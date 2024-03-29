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
from .guild_audit_service import GuildAuditService

LOG = logging.getLogger(__name__)


class Bot:
    def __init__(self, database: ThreadSafeDBConnection,
                 ts_connection_pool: ConnectionPool[TS3Facade],
                 config: Config):
        self._ts_connection_pool = ts_connection_pool  # worker connection pool
        self._config = config
        self._database_connection = database

        self.user_service = UserService(self._database_connection, self._ts_connection_pool, config)
        self.audit_service = AuditService(self._database_connection, self._ts_connection_pool, config, self.user_service)
        self.guild_service = GuildService(self._database_connection, self._ts_connection_pool, config)
        self.guild_audit_service = GuildAuditService(self._database_connection, self._ts_connection_pool, config, self.guild_service)
        self.commander_service = CommanderService(self._ts_connection_pool, self.user_service, config)
        self.reset_roster_service = ResetRosterService(self._ts_connection_pool, config)

        self.active_loop = EventLooper(self._database_connection, self._ts_connection_pool, self._config, self.user_service, self.audit_service)

    def listen_for_events(self):
        self.active_loop.start()

    def trigger_user_audit(self):
        self.audit_service.trigger_user_audit()

    def trigger_guild_audit(self):
        self.guild_audit_service.trigger_guild_audit()

    def close(self):
        self.active_loop.close()
        self.audit_service.close()
        pass
