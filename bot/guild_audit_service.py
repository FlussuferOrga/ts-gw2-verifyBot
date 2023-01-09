from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from queue import Empty, PriorityQueue

import bot.gwapi as gw2api
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import ThreadSafeDBConnection
from bot.ts import TS3Facade
from .guild_service import GuildService
from .util import ClosableLoopingThread

LOG = logging.getLogger(__name__)

# Queue Priorities, lower entries will be handles before, larger entries.

QUEUE_PRIORITY_AUDIT = 100
QUEUE_PRIORITY_JOIN = 20


@dataclass(order=True)
class GuildAuditQueueEntry:
    priority: int
    db_id: int = field(compare=False)


class GuildAuditService:
    def __init__(self, database_connection_pool: ThreadSafeDBConnection, ts_connection_pool: ConnectionPool[TS3Facade],
                 config: Config, guild_service: GuildService):
        self._guild_service = guild_service
        self._database_connection = database_connection_pool
        self._ts_connection_pool = ts_connection_pool
        self._config = config

        self._audit_queue: PriorityQueue[GuildAuditQueueEntry] = PriorityQueue()  # pylint: disable=unsubscriptable-object
        self._start_audit_queue_worker()

    def queue_guild_audit(self, priority: int, db_id: int):
        queue_entry = GuildAuditQueueEntry(priority, db_id=db_id)
        LOG.debug("Adding entry to guild audit queue for : %s", db_id)
        self._audit_queue.put(queue_entry)

    def _start_audit_queue_worker(self):
        queue = self._audit_queue

        def worker():
            item = None
            try:
                item = queue.get(timeout=5)
                LOG.debug('Working on %s:', item.db_id)
                self.audit_guild(item.db_id)
            except Empty:
                return  # empty
            except BaseException as ex:  # any error that occurs
                LOG.error("Exception during Audit Queue processing of item: %s.", item, exc_info=ex)
                queue.task_done()  # finish job anyways
                LOG.info("Remaining Queue Size: %s", queue.qsize())
            else:
                LOG.debug('Finished %s', item.db_id)
                queue.task_done()
                LOG.info("Remaining Queue Size: %s", queue.qsize())

        # start worker - in theory there could be more than one thread, but this will cause stress on the gw2-api, database and teamspeak
        self.audit_thread = ClosableLoopingThread(name="AuditQueueWorker", work=worker)
        self.audit_thread.start()
        LOG.info("Audit Worker is started and pulling audit jobs")

    def audit_guild(self, db_id: int):
        with self._database_connection.lock:
            db_guild_entity = self._database_connection.cursor.execute(
                "SELECT guild_id,guild_name,ts_group,icon_id,gw2_guild_id FROM guilds WHERE guild_id = ?", (db_id,)).fetchone()
            stored_guild_id, guild_name, ts_group, current_icon_id, gw2_guild_id = db_guild_entity if db_guild_entity is not None else [None, None, None, None, None]
        if guild_name is not None:
            guild_info = gw2api.guild_get(gw2api.guild_search(guild_name))

            if guild_info is not None:
                guild_name = guild_info.get("name")
                # guild_tag = guild_info.get("tag")
                guild_id = guild_info.get("id")
                guild_emblem = guild_info.get("emblem")

                if gw2_guild_id is None:
                    with self._database_connection.lock:
                        self._database_connection.cursor.execute("UPDATE guilds SET gw2_guild_id = ? WHERE guild_id = ?", (guild_id, db_id,))
                        self._database_connection.conn.commit()

                icon_id = self._guild_service.generate_guild_icon_id(guild_name, guild_emblem)
                if current_icon_id != icon_id:
                    self._guild_service.update_icon(db_id, guild_id, guild_name, ts_group, guild_emblem, current_icon_id)
            else:
                LOG.warning("Guild %s is not available form the gw2 api anymore", guild_name)

    def trigger_guild_audit(self):
        LOG.info("Auditing guilds")
        threading.Thread(name="FullGuildAudit", target=self._audit_guilds, daemon=True).start()

    def _audit_guilds(self):
        if not self._config.enable_guild_audit:
            LOG.debug("Guild Audit is disabled, skipping audit.")
            return

        with self._database_connection.lock:
            db_audit_list = self._database_connection.cursor.execute(
                'SELECT guild_id FROM guilds',
                ()).fetchall()

        LOG.info("Queueing Audit for %s Guilds.", len(db_audit_list))
        for audit_guild in db_audit_list:
            # Convert to single variables
            audit_guild_id = audit_guild[0]

            LOG.debug("Queueing Audit: Guild: %s", audit_guild_id)

            self.queue_guild_audit(QUEUE_PRIORITY_AUDIT, audit_guild_id)

    def close(self):
        self.audit_thread.close()
        pass
