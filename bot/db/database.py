import datetime
import logging
import os
import sqlite3
from threading import RLock

LOG = logging.getLogger(__name__)


def get_or_create_database(db_file_path: str, version: str):
    if os.path.isfile(db_file_path):
        dbc = ThreadSafeDBConnection(db_file_path)
        LOG.info("Loaded User Database...")
    else:
        dbc = ThreadSafeDBConnection(db_file_path)
        LOG.info("No User Database found...created new database!")
        _initialize_database(dbc, version)
    return dbc


def _initialize_database(dbc, version):
    with dbc.lock:
        # USERS
        dbc.cursor.execute("CREATE TABLE users(ts_db_id text primary key, account_name text, api_key text, created_date date, last_audit_date date)")
        # BOT INFO
        dbc.cursor.execute("CREATE TABLE bot_info(version text, last_succesful_audit date)")
        dbc.conn.commit()
        dbc.cursor.execute('INSERT INTO bot_info (version, last_succesful_audit) VALUES (?,?)', (version, datetime.date.today(),))
        dbc.conn.commit()
        # GUILD INFO
        dbc.cursor.execute('''CREATE TABLE guilds(
                            guild_id integer primary key autoincrement,
                            guild_name text UNIQUE,
                            ts_group text UNIQUE
                            icon_id integer)''')
        dbc.conn.commit()

        # GUILD IGNORES
        dbc.cursor.execute('''CREATE TABLE guild_ignores(
                            guild_ignore_id integer primary key autoincrement,
                            guild_id integer,
                            ts_db_id text,
                            ts_name text,
                            FOREIGN KEY(guild_id) REFERENCES guilds(guild_id),
                            UNIQUE(guild_id, ts_db_id))''')
        dbc.conn.commit()


class ThreadSafeDBConnection:
    def __init__(self, db_name):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
        self.cursor = self.conn.cursor()
        self.lock = RLock()

    def close(self):
        self.conn.close()
