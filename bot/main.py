#!/usr/bin/python
import logging
from argparse import Namespace
from typing import Tuple

import configargparse
import schedule
import time  # time for sleep function
import ts3

from bot import Bot
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import get_or_create_database
from bot.rest import server
from bot.ts import TS3Facade, create_connection
from bot.util import RepeatTimer

LOG = logging.getLogger(__name__)


def main(args: Namespace):  #
    LOG.info("Initializing script....")

    config = Config(args.config_path)

    # setup ressoruces
    database = get_or_create_database(config.db_file_name, config.current_version)
    ts_connection_pool: ConnectionPool[TS3Facade] = create_connection_pool(config)

    # auditjob trigger + keepalives using the "scheduler" lib
    job_thread = _create_job_thread()
    job_thread.start()

    # create bot instance and let it loop
    _continuous_loop(config, database, ts_connection_pool)

    # release resources gracefully
    job_thread.cancel()

    LOG.info("Stopping Connection Pool...")
    ts_connection_pool.close()

    LOG.info("Closing Database Connection...")
    database.close()

    LOG.info("Bye!")


def _create_job_thread():
    job_thread = RepeatTimer(10.0, schedule.run_pending)
    job_thread.setDaemon(True)
    job_thread.setName("schedule_run_pending")
    return job_thread


def _continuous_loop(config, database, ts_connection_pool):
    #######################################
    # Begins the connect to Teamspeak
    #######################################
    bot_loop_forever = True
    while bot_loop_forever:
        try:
            LOG.info("Connecting to Teamspeak server...")

            with ts_connection_pool.item() as ts_facade:
                bot_instance = Bot(database, ts_connection_pool, ts_facade, config)

                http_server = server.create_http_server(bot_instance, port=config.ipc_port)
                try:
                    http_server.start()

                    LOG.info("BOT Database Audit policies initiating.")
                    # Always audit users on initialize if user audit date is up (in case the script is reloaded several
                    # times before audit interval hits, so we can ensure we maintain user database accurately)
                    bot_instance.trigger_user_audit()

                    #                     # Set audit schedule job to run in X days
                    audit_job = schedule.every(config.audit_interval).days.do(bot_instance.trigger_user_audit)

                    bot_instance.listen_for_events()
                finally:
                    if audit_job is not None:
                        schedule.cancel_job(audit_job)

                    if http_server is not None:
                        LOG.info("Stopping Http Server")
                        http_server.stop()
        except (ConnectionRefusedError, ts3.query.TS3TransportError) as ex:
            LOG.warning("Unable to reach teamspeak server..trying again in %s seconds...", config.bot_sleep_conn_lost, exc_info=ex)
            time.sleep(config.bot_sleep_conn_lost)
        except (KeyboardInterrupt, SystemExit):
            LOG.info("Shutdown signal received. Shutting down:")
            bot_loop_forever = False  # stop loop


def create_connection_pool(config):
    return ConnectionPool(create=lambda: TS3Facade(create_connection(config, config.bot_nickname)),
                          destroy_function=lambda obj: obj.close(),
                          test_function=lambda obj: obj.is_connected(),
                          max_size=config.pool_size,
                          max_usage=config.pool_max_usage, idle=config.pool_tti, ttl=config.pool_ttl)


def parse_args() -> Tuple[Namespace, configargparse.ArgumentParser]:
    parser: configargparse.ArgumentParser = configargparse.ArgParser(description='ts-gw2-verifyBot')
    parser.add_argument('-c', '--config-path',
                        env_var="CONFIG_PATH",
                        dest='config_path', type=str,
                        help='Config file location',
                        # is_config_file=True, # this is also input for other config entries
                        default="./bot.conf")
    parser.add_argument('--logging-level',
                        env_var="LOGGING_LEVEL",
                        dest='logging_level', type=str,
                        help='Logging Level',
                        default="DEBUG")
    parser.add_argument('--logging-file',
                        env_var="LOGGING_FILE",
                        dest='logging_file', type=str,
                        help='Logging File, disabled when empty',
                        default="./ts3bot.log")
    args: Namespace = parser.parse_args()
    return args, parser

#######################################
