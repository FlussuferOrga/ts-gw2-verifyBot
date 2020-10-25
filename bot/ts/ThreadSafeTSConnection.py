import logging
from threading import RLock
from typing import Callable, Tuple, TypeVar

import schedule
import ts3
from ts3.query import TS3ServerConnection, TS3TransportError

from bot.config import Config

LOG = logging.getLogger(__name__)

R = TypeVar('R')


def default_exception_handler(ex):
    """ prints the trace and returns the exception for further inspection """
    LOG.debug("Exception caught in default_exception_handler: ", exc_info=ex)
    return ex


def raise_exception_handler(ex):
    """ raises the exception for further inspection """
    raise ex


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
        return "%s://%s:%s@%s:%s" % (self._protocol, self._user, self._password, self._host, str(self._port))

    def __init__(self, protocol, user, password, host, port, keepalive_interval=None, server_id=None, bot_nickname=None, known_hosts_file: str = None):
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
        self._protocol = protocol
        self._user = user
        self._password = password
        self._host = host
        self._port = port
        self._keepalive_interval = int(keepalive_interval)
        self._server_id = server_id
        self._known_hosts_file = known_hosts_file

        self._bot_nickname = bot_nickname + '-' + str(id(self))
        self.lock = RLock()
        self.ts_connection = None  # done in init()
        self._keepalive_job = None
        self._init()

        LOG.info("New Connection %s is ready.", self)

    def _init(self):
        with self.lock:  # lock for good measure
            if self.ts_connection is not None:
                pass

            tp_args = dict()
            if self._protocol == "ssh" and self._known_hosts_file is not None:
                tp_args["host_key"] = self._known_hosts_file

            self.ts_connection = ts3.query.TS3ServerConnection(self.uri, tp_args=tp_args)

            # This hack allows using the "quit" command, so the bot does not appear as "timed out" in the Ts3 Client & Server log
            self.ts_connection.COMMAND_SET = set(self.ts_connection.COMMAND_SET)  # creat copy of frozenset
            self.ts_connection.COMMAND_SET.add('quit')  # add command

            if self._keepalive_interval is not None:
                self._keepalive_job = schedule.every(self._keepalive_interval).seconds.do(self.keepalive)

            if self._server_id is not None:
                self.ts3exec(lambda tc: tc.exec_("use", sid=self._server_id))

            if self._bot_nickname is not None:
                self.force_rename(self._bot_nickname)

    def __str__(self):
        return f"ThreadSafeTSConnection[{self._bot_nickname}]"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()
        return None

    def keepalive(self):
        LOG.info("Keepalive %s", self)
        with self.lock:
            try:
                self.ts3exec_raise(lambda tc: tc.send_keepalive())
            except Exception as ex:
                LOG.warning("Exception during Keepalive of %s", self, exc_info=ex)

    def is_connected(self):
        return self.ts3exec_raise(lambda tc: tc.is_connected())

    def is_healthy(self):
        if not self.is_connected():
            raise TS3TransportError("Connection is closed")
        try:
            # by actually sending some bytes we can test of the socket is responsive.
            self.ts3exec_raise(lambda tc: tc.send_keepalive())
        except Exception as ex:
            raise TS3TransportError("Connection is unhealthy") from ex
        else:
            return True

    def ts3exec_raise(self, handler: Callable[[TS3ServerConnection], R]) -> R:
        return self.ts3exec(handler, raise_exception_handler)[0]

    def ts3exec(self,
                handler: Callable[[TS3ServerConnection], R],
                exception_handler=default_exception_handler) -> Tuple[R, Exception]:  # eh = lambda ex: print(ex)):
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
        with self.lock:
            failed = True
            fails = 0
            res = None
            exres = None
            while failed and fails < ThreadSafeTSConnection.RETRIES:
                failed = False
                try:
                    res = handler(self.ts_connection)
                # except ts3.query.TS3TransportError as ts3tex:
                #     failed = True
                #     fails += 1
                #     if fails >= ThreadSafeTSConnection.RETRIES:
                #         LOG.error("Critical error on transport level! Closing this Connection.", exc_info=ts3tex)
                #         self.close()
                #         raise ts3tex
                #     else:
                #         LOG.error("Error on transport level! Attempt %s to send the command again.", str(fails), )
                except Exception as ex:
                    exres = exception_handler(ex)
        return res, exres

    def close(self):
        with self.lock:
            LOG.info("Closing %s", self)
            if self._keepalive_job is not None:
                schedule.cancel_job(self._keepalive_job)

            # This hack allows using the "quit" command, so the bot does not appear as "timed out" in the Ts3 Client & Server log
            if self.ts_connection is not None and hasattr(self.ts_connection, "is_connected"):
                try:
                    if self.is_healthy():
                        quit_query = self.ts_connection.query("quit")
                        self.ts_connection.exec_query(query=quit_query, timeout=2)  # immediately quit
                except (ts3.query.TS3TimeoutError, ts3.query.TS3TransportError):
                    pass
                except Exception as ex:
                    LOG.debug("Exception during closing the connection. This is usually not a problem.", exc_info=ex)
                finally:
                    self.ts_connection = None

    def _gentle_rename(self, nickname):
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

    def force_rename(self, target_nickname):
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
                    target_nickname = self._gentle_rename(target_nickname)
                    LOG.info("Renamed self to '%s'.", target_nickname)
                else:
                    self.ts3exec_raise(lambda tc: tc.exec_("clientupdate", client_nickname=target_nickname))
        else:
            LOG.info("No rename necessary")
        self._bot_nickname = target_nickname
        return self._bot_nickname


def create_connection(config: Config, nickname: str) -> ThreadSafeTSConnection:
    return ThreadSafeTSConnection(config.protocol,
                                  config.user, config.passwd,
                                  config.host, config.port,
                                  config.keepalive_interval,
                                  config.server_id,
                                  nickname,
                                  known_hosts_file=config.known_hosts_file)
