#!/usr/bin/python
import logging
from argparse import Namespace
from typing import Optional, Tuple

import configargparse as configargparse
import schedule
import sys
import time  # time for sleep function
import ts3
from ts3.response import TS3Event

from bot import Bot
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import get_or_create_database
from bot.rest import HTTPServer
from bot.rest import server
from bot.ts import Channel, TS3Facade, create_connection

LOG = logging.getLogger(__name__)

# Global states
verify_channel: Optional[Channel] = None
http_server: Optional[HTTPServer] = None


def main(args: Namespace):  #
    global verify_channel, http_server

    LOG.info("Initializing script....")

    config = Config(args.config_path)
    database = get_or_create_database(config.db_file_name, config.current_version)

    ts_connection_pool: ConnectionPool[TS3Facade] = create_connection_pool(config)

    #######################################
    # Begins the connect to Teamspeak
    #######################################
    bot_loop_forever = True
    while bot_loop_forever:
        try:
            try:
                LOG.info("Connecting to Teamspeak server...")

                with ts_connection_pool.item() as ts_facade:
                    bot_instance = Bot(database, ts_connection_pool, ts_facade, config)

                    http_server = server.create_http_server(bot_instance, port=config.ipc_port)
                    http_server.start()

                    LOG.info("BOT loaded into server (%s) as %s (%s). Nickname '%s'", config.server_id, bot_instance.name, bot_instance.client_id, bot_instance.nickname)

                    # Find the verify channel
                    verify_channel = find_verify_channel(ts_facade, config.channel_name)

                    # Move ourselves to the Verify chanel and register for text events
                    move_to_channel(ts_facade, verify_channel, bot_instance.client_id, config.channel_name)

                    ts_facade.server_notify_register(["textchannel", "textprivate", "server"])

                    # Send message to the server that the BOT is up
                    # main_ts3conn.exec_("sendtextmessage", targetmode=3, target=server_id, msg=locale.get("bot_msg",(bot_nickname,)))
                    LOG.info("BOT is now registered to receive messages!")

                    LOG.info("BOT Database Audit policies initiating.")
                    # Always audit users on initialize if user audit date is up (in case the script is reloaded several
                    # times before audit interval hits, so we can ensure we maintain user database accurately)
                    bot_instance.trigger_user_audit()

                    # Set audit schedule job to run in X days
                    schedule.every(config.audit_interval).days.do(bot_instance.trigger_user_audit)

                    LOG.info("BOT now online,sending broadcast.")
                    bot_instance.broadcastMessage()  # Send initial message into channel

                    # debug
                    # BOT.setResetroster(main_ts3conn, "2020-04-01",
                    #                    red = ["the name with the looooong name"],
                    #                    green = ["another really well hung name", "len", "oof. tat really a long one duuuude"],
                    #                    blue = ["[DUST] dude", "[DUST] anotherone", "[DUST] thecrusty dusty mucky man"],
                    #                    ebg = [])
                    # testguilds = [
                    #     ("Unleash Chaos", "uC", "uC"),
                    #     ("Requiem of Execution", "RoE", "RoE"),
                    #     ("Zum Henker", "ZH", "ZH"),
                    #     ("Formation Wolke", "Zerg", "Zerg."),
                    #     ("Zergs Rebellion", "Zerg", "Zerg"),
                    #     ("Flussufer Beach Boys", "FBB", "FBB"),
                    #     ("Ups Falsche Taste", "UPS", "UPS"),
                    #     ("Rising River", "Side", "Side"),
                    #     ("Demons of Dawn", "DoD", "DoD")
                    # ]

                    # for gname, gtag, ggroup in testguilds:
                    #    BOT.removeGuild(gname, gtag, ggroup)
                    #    BOT.createGuild(gname, gtag, ggroup, ["len.1879", "jey.1111"])

                    # Forces script to loop forever while we wait for events to come in, unless connection timed out. Then it should loop a new bot into creation.
                    LOG.info("BOT now idle, waiting for requests.")
                    while ts_facade.is_connected():
                        # auditjob + keepalive check
                        schedule.run_pending()
                        response: TS3Event
                        try:
                            response = ts_facade.wait_for_event(timeout=config.bot_sleep_idle)
                            event_type: str = response.event
                            event_data = response.parsed[0]
                            if event_type == 'notifytextmessage':
                                if "msg" in event_data:
                                    # text message
                                    bot_instance.messageEventHandler(event_data)  # handle event
                            elif event_type == 'notifycliententerview':
                                if event_data["client_type"] == '1':  # server query client
                                    continue
                                else:
                                    bot_instance.loginEventHandler(event_data)  # handle event
                            elif event_type == 'notifyclientleftview':  # client left
                                continue
                            else:
                                LOG.warning("Unhandled Event: %s", event_type)
                        except Exception as ex:
                            LOG.error("Error while trying to handle event %s: %s", event_type, str(event_data), exc_info=ex)

                LOG.warning("It appears the BOT has lost connection to teamspeak. Trying to restart connection in %s seconds....", config.bot_sleep_conn_lost)
                time.sleep(config.bot_sleep_conn_lost)

            except (ConnectionRefusedError, ts3.query.TS3TransportError):
                LOG.warning("Unable to reach teamspeak server..trying again in %s seconds...", config.bot_sleep_conn_lost)
                time.sleep(config.bot_sleep_conn_lost)
        except (KeyboardInterrupt, SystemExit):
            LOG.info("Stopping...")
            http_server.stop()
            sys.exit(0)


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


def move_to_channel(ts_facade, channel: Channel, client_id, channel_name):
    chnl_err = ts_facade.client_move(client_id=client_id, channel_id=channel.channel_id)
    if chnl_err:
        LOG.warning("BOT Attempted to join channel '%s' (%s): %s", channel_name, channel.channel_id, chnl_err.resp.error["msg"])
    else:
        LOG.info("BOT has joined channel '%s' (%s).", channel_name, channel.channel_id)


def find_verify_channel(ts_repository, channel_name):
    found_channel = None
    while found_channel is None:
        found_channel = ts_repository.channel_find(channel_name)
        if found_channel is None:
            LOG.warning("Unable to locate channel with name '%s'. Sleeping for 10 seconds...", channel_name)
            time.sleep(10)
        else:
            return found_channel

#######################################
