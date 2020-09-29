from __future__ import annotations

import datetime
import logging
import threading
from dataclasses import dataclass, field
from datetime import date
from queue import PriorityQueue

from bot.TS3Auth import AuthRequest
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import ThreadSafeDBConnection
from bot.ts import TS3Facade, User
from .user_service import UserService

LOG = logging.getLogger(__name__)

# Queue Priorities, lower entries will be handles before, larger entries.

QUEUE_PRIORITY_AUDIT = 100
QUEUE_PRIORITY_JOIN = 20


@dataclass(order=True)
class AuditQueueEntry:
    priority: int
    account_name: str = field(compare=False)
    api_key: str = field(compare=False)
    client_unique_id: str = field(compare=False)


class AuditService:
    def __init__(self, database_connection_pool: ThreadSafeDBConnection, ts_connection_pool: ConnectionPool[TS3Facade], config: Config, user_service: UserService):
        self._user_service = user_service
        self._database_connection = database_connection_pool
        self._ts_connection_pool = ts_connection_pool
        self._config = config

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
                self._user_service.update_guild_tags(ts_facade, User(ts_facade, unique_id=client_unique_id), auth)
            with self._database_connection.lock:
                self._database_connection.cursor.execute("UPDATE users SET last_audit_date = ? WHERE ts_db_id= ?", ((date.today()), client_unique_id,))
                self._database_connection.conn.commit()
        else:
            LOG.info("User %s is no longer on our server. Removing access....", account_name)
            self._user_service.removePermissions(client_unique_id)
            self._user_service.remove_user_from_db(client_unique_id)

    def trigger_user_audit(self):
        LOG.info("Auditing users")
        threading.Thread(name="FullAudit", target=self._audit_users, daemon=True).start()

    def _audit_users(self):
        self.c_audit_date = datetime.date.today()  # Update current date everytime run

        with self._database_connection.lock:
            db_audit_list = self._database_connection.cursor.execute('SELECT * FROM users').fetchall()
        for audit_user in db_audit_list:

            # Convert to single variables
            audit_ts_id = audit_user[0]
            audit_account_name = audit_user[1]
            audit_api_key = audit_user[2]
            # audit_created_date = audit_user[3]
            audit_last_audit_date = audit_user[4]

            LOG.debug("Audit: User %s", audit_account_name)
            LOG.debug("TODAY |%s|  NEXT AUDIT |%s|", self.c_audit_date, audit_last_audit_date + datetime.timedelta(days=self._config.audit_period))

            if self.c_audit_date >= audit_last_audit_date + datetime.timedelta(days=self._config.audit_period):  # compare audit date
                with self._ts_connection_pool.item() as ts_connection:
                    ts_uuid = ts_connection.client_db_id_from_uid(audit_ts_id)
                if ts_uuid is None:
                    LOG.info("User %s is not found in TS DB and could be deleted.", audit_account_name)
                    self._database_connection.cursor.execute("UPDATE users SET last_audit_date = ? WHERE ts_db_id= ?", ((datetime.date.today()), audit_ts_id,))
                    # self.removeUserFromDB(audit_ts_id)
                else:
                    LOG.info("User %s is due for auditing! Queueing", audit_account_name)
                    self.queue_user_audit(QUEUE_PRIORITY_AUDIT, audit_account_name, audit_api_key, audit_ts_id)

        with self._database_connection.lock:
            self._database_connection.cursor.execute('INSERT INTO bot_info (last_succesful_audit) VALUES (?)', (self.c_audit_date,))
            self._database_connection.conn.commit()

    def audit_user_on_join(self, client_unique_id):
        db_entry = self._user_service.getUserDBEntry(client_unique_id)
        if db_entry is not None:
            account_name = db_entry["account_name"]
            api_key = db_entry["api_key"]
            self.queue_user_audit(QUEUE_PRIORITY_JOIN, account_name=account_name, api_key=api_key, client_unique_id=client_unique_id)
