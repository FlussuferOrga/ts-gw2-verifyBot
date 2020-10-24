#!/usr/bin/python
import logging

from bot.config import Config
from bot.db import ThreadSafeDBConnection
from bot.ts import TS3Facade
from .audit_service import AuditService
from .commander_service import CommanderService
from .connection_pool import ConnectionPool
from .event_looper import EventLooper
from .guild_service import GuildService
from .reset_roster_service import ResetRosterService
from .user_service import UserService

LOG = logging.getLogger(__name__)


class Bot:

    def __init__(self, database: ThreadSafeDBConnection,
                 ts_connection_pool: ConnectionPool[TS3Facade],
                 ts_facade: TS3Facade,
                 config: Config):
        self._ts_facade = ts_facade  # use this only for representative Tasks such as sending messages to a user. Use a connection from the pool for worker tasks
        self._ts_connection_pool = ts_connection_pool  # worker connection pool
        self._config = config
        self._database_connection = database

        self.user_service = UserService(self._database_connection, self._ts_connection_pool, config)
        self.audit_service = AuditService(self._database_connection, self._ts_connection_pool, config, self.user_service)
        self.guild_service = GuildService(self._database_connection, self._ts_connection_pool, config)
        self.commander_service = CommanderService(self._ts_connection_pool, self.user_service, config)
        self.reset_roster_service = ResetRosterService(self._ts_connection_pool, config)

    def listen_for_events(self):
        active_loop = EventLooper(self._database_connection, self._ts_connection_pool, self._config, self.user_service, self.audit_service)
        active_loop.start()
        del active_loop

    def trigger_user_audit(self):
        self.audit_service.trigger_user_audit()
