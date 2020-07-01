import logging
from threading import RLock
from typing import Callable, Tuple

import schedule
import ts3
from ts3.query import TS3ServerConnection
from ts3.response import TS3QueryResponse, TS3Response

LOG = logging.getLogger(__name__)


def default_exception_handler(ex):
    """ prints the trace and returns the exception for further inspection """
    LOG.debug("Exception caught in default_exception_handler: ", exc_info=ex)
    return ex


def signal_exception_handler(ex):
    """ returns the exception without printing it, useful for expected exceptions, signaling that an exception occurred """
    return ex


def ignore_exception_handler(ex):
    """ acts as if no exception was raised, equivalent to except: pass"""
    return None


class ThreadSafeTSConnection:
    RETRIES = 3

    @property
    def uri(self):
        return "telnet://%s:%s@%s:%s" % (self._user, self._password, self._host, str(self._port))

    def __init__(self, user, password, host, port, keepalive_interval=None, server_id=None, bot_nickname=None):
        """
        Creates a new threadsafe TS3 connection.
        user: user to connect as
        password: password to connect to user with
        host: host of TS3 server
        port: port for server queries
        keepalive_interval: interval in which the keepalive is sent to the ts3 server
        server_id: the server id of the TS3 server we want to address, in case we have multiple.
                   Note that the server id HAS to be selected at some point, using the "use" command.
                   It has just been wrapped in here to allow for more convenient copying of the
                   TS3 connection where the appropriate server is selected automatically.
        bot_nickname: nickname for the bot. Could be suffixed, see gentleRename. If None is passed,
                      no naming will take place.
        """
        self._user = user
        self._password = password
        self._host = host
        self._port = port
        self._keepalive_interval = int(keepalive_interval)
        self._server_id = server_id
        self._bot_nickname = bot_nickname
        self.lock = RLock()
        self.ts_connection = None  # done in init()
        self.init()

    def init(self):
        if self.ts_connection is not None:
            try:
                self.ts_connection.close()
            except Exception:
                pass  # may already be closed, doesn't matter.
        self.ts_connection = ts3.query.TS3ServerConnection(self.uri)
        if self._keepalive_interval is not None:
            schedule.cancel_job(self.keepalive)  # to avoid accumulating keepalive calls during re-inits
            schedule.every(self._keepalive_interval).seconds.do(self.keepalive)
        if self._server_id is not None:
            self.ts3exec(lambda tc: tc.exec_("use", sid=self._server_id))
        if self._bot_nickname is not None:
            self.forceRename(self._bot_nickname)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def keepalive(self):
        self.ts3exec(lambda tc: tc.send_keepalive())

    def ts3exec(self,
                handler: Callable[[TS3ServerConnection], TS3QueryResponse],
                exception_handler=lambda ex: default_exception_handler(ex)) -> Tuple[TS3Response, Exception]:  # eh = lambda ex: print(ex)):
        """
        Excecutes a query() or exec_() on the internal TS3 connection.
        handler: a function ts3.query.TS3ServerConnection -> any
        exception_handler: a function Exception -> any. None will be interpreted as not having encountered an exception.
                           The default handler prints the stacktrace for the exception and returns the exception itself.
                           This changes the workflow of executing erroring code: instead of try-catching we need to
                           decompose the tuple returned from this function and check if the exception result is anything
                           but None. E.g.:

                            try:
                               res = ts3con.query(...)
                            except Exception as ex:
                                # error handling

                           becomes

                            res,ex = threadsafe_ts3con.ts3exec(lambda tc: tc.query(...))
                            if ex:
                                # error handling

                           Note that the exception handler is only executed iff an exception is actually
                           being handled!

        returns a tuple with the results of the two handlers (result first, exception result second).
        """
        reinit = False
        with self.lock:
            failed = True
            fails = 0
            res = None
            exres = None
            while failed and fails < ThreadSafeTSConnection.RETRIES:
                failed = False
                try:
                    res = handler(self.ts_connection)
                except ts3.query.TS3TransportError:
                    failed = True
                    fails += 1
                    LOG.error("Critical error on transport level! Attempt %s to restart the connection and send the command again.", str(fails), )
                    reinit = True
                except Exception as ex:
                    exres = exception_handler(ex)
        if reinit:
            self.init()
        return res, exres

    def close(self):
        self.ts3exec(lambda tc: tc.close())

    def copy(self):
        tsc = ThreadSafeTSConnection(self._user, self._password, self._host, self._port, self._keepalive_interval, self._server_id, None)
        # make sure to
        # 1. not pass bot_nickname to the constructor, or the child (copy) would call forceRename and attempt to kick the parent
        # 2. gently rename the copy afterwards
        tsc.gentleRename(self._bot_nickname)
        return tsc

    def gentleRename(self, nickname):
        """
        Renames self to nickname, but attaches a running counter
        to the name if the nickname is already taken.
        """
        i = 1
        new_nick = "%s(%d)" % (nickname, i)
        while not self.ts3exec(lambda tc: tc.query("clientfind", pattern=new_nick).first(), signal_exception_handler)[1]:
            i += 1
            new_nick = "%s(%d)" % (nickname, i)
        new_nick = "%s(%d)" % (nickname, i)
        self.ts3exec(lambda tc: tc.exec_("clientupdate", client_nickname=new_nick))
        self._bot_nickname = new_nick
        return self._bot_nickname

    def forceRename(self, nickname):
        """
        Attempts to forcefully rename self.
        If the chosen nickname is already taken, the bot will attempt to kick that user.
        If that fails the bot will fall back to gentle renaming itself.
        """
        imposter, free = self.ts3exec(lambda tc: tc.query("clientfind", pattern=nickname).first(), signal_exception_handler)  # check if nickname is already in use
        if not free:  # error occurs if no such user was found -> catching no exception means the name is taken
            _, ex = self.ts3exec(lambda tc: tc.exec_("clientkick", reasonid=5, reasonmsg="Reserved Nickname", clid=imposter.get("clid")), signal_exception_handler)
            if ex:
                LOG.warning(
                    "Renaming self to '%s' after kicking existing user with reserved name failed."
                    " Warning: this usually only happens for serverquery logins, meaning you are running multiple bots or you"
                    " are having stale logins from crashed bot instances on your server. Only restarts can solve the latter.",
                    nickname)
            else:
                LOG.info("Kicked user who was using the reserved registration bot name '%s'.", nickname)
            nickname = self.gentleRename(nickname)
            LOG.info("Renamed self to '%s'.", nickname)
        else:
            self.ts3exec(lambda tc: tc.exec_("clientupdate", client_nickname=nickname))
            LOG.info("Forcefully renamed self to '%s'.", nickname)
        self._bot_nickname = nickname
        return self._bot_nickname
