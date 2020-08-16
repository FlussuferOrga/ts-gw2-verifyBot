import logging
from threading import RLock
from typing import Callable, Tuple, TypeVar

import schedule
import ts3
from ts3.query import TS3ServerConnection

from bot.config import Config

LOG = logging.getLogger(__name__)

R = TypeVar('R')


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
        self._bot_nickname = bot_nickname + '-' + str(id(self))
        self.lock = RLock()
        self.ts_connection = None  # done in init()
        self._keepalive_job = None
        self.init()

    def init(self):
        if self.ts_connection is not None:
            try:
                self.ts_connection.close()
            except Exception:
                pass  # may already be closed, doesn't matter.
        self.ts_connection = ts3.query.TS3ServerConnection(self.uri)

        if self._keepalive_interval is not None:
            if self._keepalive_job is not None:
                schedule.cancel_job(self._keepalive_job)  # to avoid accumulating keepalive calls during re-inits
            self._keepalive_job = schedule.every(self._keepalive_interval).seconds.do(self.keepalive)
        if self._server_id is not None:
            self.ts3exec(lambda tc: tc.exec_("use", sid=self._server_id))
        if self._bot_nickname is not None:
            self.forceRename(self._bot_nickname)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()
        return None

    def keepalive(self):
        LOG.info(f"Keepalive Ts Connection {self._bot_nickname}")
        self.ts3exec(lambda tc: tc.send_keepalive())

    def ts3exec(self,
                handler: Callable[[TS3ServerConnection], R],
                exception_handler=lambda ex: default_exception_handler(ex)) -> Tuple[R, Exception]:  # eh = lambda ex: print(ex)):
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
        if self._keepalive_job is not None:
            schedule.cancel_job(self._keepalive_job)

        # This hack allows using the "quit" command, so the bot does not appear as "timed out" in the Ts3 Client & Server log
        if self.ts_connection is not None:
            self.ts_connection.COMMAND_SET = set(self.ts_connection.COMMAND_SET)  # creat copy of frozenset
            self.ts_connection.COMMAND_SET.add('quit')  # add command

            self.ts_connection.exec_("quit")  # send quit
            self.ts_connection.close()  # immediately quit

            del self.ts_connection

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

    def forceRename(self, target_nickname):
        """
        Attempts to forcefully rename self.
        If the chosen nickname is already taken, the bot will attempt to kick that user.
        If that fails the bot will fall back to gentle renaming itself.
        """
        whoami_response, _ = self.ts3exec(lambda tc: tc.query("whoami").first())
        imposter, error = self.ts3exec(lambda tc: tc.query("clientfind", pattern=target_nickname).first(), signal_exception_handler)  # check if nickname is already in use

        if whoami_response['client_nickname'] != target_nickname:
            if error:
                if error.resp.error.get('id') == '512':  # no result
                    self.ts3exec(lambda tc: tc.exec_("clientupdate", client_nickname=target_nickname))
                    LOG.info("Forcefully renamed self to '%s'.", target_nickname)
                else:
                    LOG.error("Error on rename when searching for users", exc_info=error)
            else:
                if whoami_response['client_id'] != imposter['clid']:
                    _, ex = self.ts3exec(lambda tc: tc.exec_("clientkick", reasonid=5, reasonmsg="Reserved Nickname", clid=imposter.get("clid")), signal_exception_handler)
                    if ex:
                        LOG.warning(
                            "Renaming self to '%s' after kicking existing user with reserved name failed."
                            " Warning: this usually only happens for serverquery logins, meaning you are running multiple bots or you"
                            " are having stale logins from crashed bot instances on your server. Only restarts can solve the latter.",
                            target_nickname)
                    else:
                        LOG.info("Kicked user who was using the reserved registration bot name '%s'.", target_nickname)
                    target_nickname = self.gentleRename(target_nickname)
                    LOG.info("Renamed self to '%s'.", target_nickname)
                else:
                    self.ts3exec(lambda tc: tc.exec_("clientupdate", client_nickname=target_nickname))
        else:
            LOG.info("No rename necessary")
        self._bot_nickname = target_nickname
        return self._bot_nickname


def create_connection(config: Config, nickname: str) -> ThreadSafeTSConnection:
    return ThreadSafeTSConnection(config.user, config.passwd,
                                  config.host, config.port,
                                  config.keepalive_interval,
                                  config.server_id,
                                  nickname)
