from ts3.query import TS3InvalidCommandError, TS3ServerConnection
from ts3.query_builder import TS3QueryBuilder


class ExtendedTS3QueryBuilder(TS3QueryBuilder):
    _fallback_timeout = None
    _timeout = None

    def __init__(self, cmd, ts3conn=None, pipes=None, fallback_timeout=60):
        super().__init__(cmd, ts3conn, pipes)
        self._fallback_timeout = fallback_timeout

    def timeout(self, timeout):
        """
        Adds a timeout to the request
        """
        self._timeout = timeout
        return self

    def fetch(self):
        actual_timeout = self._timeout if self._timeout is not None else self._fallback_timeout
        return self._ts3conn.exec_query(self, timeout=actual_timeout)


class ExtendedTS3ServerConnection(TS3ServerConnection):

    def query(self, cmd, *options, **params) -> ExtendedTS3QueryBuilder:
        if cmd not in self.COMMAND_SET:
            raise TS3InvalidCommandError(cmd, self.COMMAND_SET)
        return ExtendedTS3QueryBuilder(ts3conn=self, cmd=cmd).pipe(*options, **params)
