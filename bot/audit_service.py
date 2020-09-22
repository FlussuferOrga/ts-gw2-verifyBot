from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date
from queue import PriorityQueue

from bot import TS3Bot
from bot.TS3Auth import AuthRequest
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import ThreadSafeDBConnection
from bot.ts import TS3Facade, User

LOG = logging.getLogger(__name__)


@dataclass(order=True)
class AuditQueueEntry:
    priority: int
    account_name: str = field(compare=False)
    api_key: str = field(compare=False)
    client_unique_id: str = field(compare=False)


class AuditService:
    def __init__(self, database_connection_pool: ThreadSafeDBConnection, ts_connection_pool: ConnectionPool[TS3Facade], config: Config, bot: TS3Bot):
        self._database_connection = database_connection_pool
        self._ts_connection_pool = ts_connection_pool
        self._config = config
        self._bot = bot

        self._audit_queue: PriorityQueue[AuditQueueEntry] = PriorityQueue()  # pylint: disable=unsubscriptable-object
        self._start_audit_queue_worker()

    def queue_user_audit(self, priority: int, account_name: str, api_key: str, client_unique_id: str):
        queue_entry = AuditQueueEntry(priority, account_name=account_name, api_key=api_key, client_unique_id=client_unique_id)
        LOG.debug("Adding entry to audit queue for : %s", account_name)
        self._audit_queue.put(queue_entry)

    def _start_audit_queue_worker(self):
        def worker():
            LOG.info("Audit Worker is ready and pulling audit jobs")
            while True:
                item = self._audit_queue.get()
                LOG.debug('Working on %s. %s still in queue.', item.account_name, self._audit_queue.qsize())
                self.audit_user(item.account_name, item.api_key, item.client_unique_id)
                LOG.debug('Finished %s', item.account_name)
                self._audit_queue.task_done()

                # Log queue size if over ten
                qsize: int = self._audit_queue.qsize()
                if qsize >= 10:
                    LOG.info("Queue Size: %s", qsize)

        # start worker - in theory there could be more than one thread, but this will cause stress on the gw2-api, database and teamspeak
        threading.Thread(name="AuditQueueWorker", target=worker, daemon=True).start()

    def audit_user(self, account_name, api_key, client_unique_id):
        auth = AuthRequest(api_key, self._config.required_servers, int(self._config.required_level), account_name)
        if auth.success:
            LOG.info("User %s is still on %s. Successful audit!", account_name, auth.world.get("name"))
            with self._ts_connection_pool.item() as ts_facade:
                self._bot.updateGuildTags(ts_facade, User(ts_facade, unique_id=client_unique_id), auth)
            with self._database_connection.lock:
                self._database_connection.cursor.execute("UPDATE users SET last_audit_date = ? WHERE ts_db_id= ?", ((date.today()), client_unique_id,))
                self._database_connection.conn.commit()
        else:
            LOG.info("User %s is no longer on our server. Removing access....", account_name)
            self._bot.removePermissions(client_unique_id)
            self._bot.removeUserFromDB(client_unique_id)
