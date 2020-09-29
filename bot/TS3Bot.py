#!/usr/bin/python
import datetime  # for date strings
import logging

from bot.config import Config
from bot.db import ThreadSafeDBConnection
from bot.ts import TS3Facade
from bot.util import StringShortener
from .audit_service import AuditService
from .commander_service import CommanderService
from .connection_pool import ConnectionPool
from .event_looper import EventLooper
from .guild_service import GuildService
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

        self.c_audit_date = datetime.date.today()

    def set_reset_roster(self, date, red=[], green=[], blue=[], ebg=[]):
        leads = ([], red, green, blue, ebg)  # keep RGB order! EBG as last! Pad first slot (header) with empty list

        with self._ts_connection_pool.item() as facade:
            channels = [(p, c.replace("$DATE", date)) for p, c in self._config.reset_channels]
            for i in range(len(channels)):
                pattern, clean = channels[i]
                lead = leads[i]

                TS3_MAX_SIZE_CHANNEL_NAME = 40
                shortened = StringShortener(TS3_MAX_SIZE_CHANNEL_NAME - len(clean)).shorten(lead)
                newname = "%s%s" % (clean, ", ".join(shortened))

                channel = facade.channel_find(pattern)
                if channel is None:
                    LOG.warning("No channel found with pattern '%s'. Skipping.", pattern)
                    return

                _, ts3qe = facade.channel_edit(channel_id=channel.channel_id, new_channel_name=newname)
                if ts3qe is not None and ts3qe.resp.error["id"] == "771":
                    # channel name already in use
                    # probably not a bug (channel still unused), but can be a config problem
                    LOG.info("Channel '%s' already exists. This is probably not a problem. Skipping.", newname)
        return 0

    def listen_for_events(self):
        active_loop = EventLooper(self._database_connection, self._ts_connection_pool, self._config, self.user_service, self.audit_service)
        active_loop.start()
        del active_loop
        pass

    def trigger_user_audit(self):
        self.audit_service.trigger_user_audit()
        pass
