#!/usr/bin/python
import argparse
import logging
from typing import Optional

import schedule
import sys
import time  # time for sleep function
import ts3
from ts3.response import TS3Response

from bot import Bot
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import get_or_create_database
from bot.rest import HTTPServer
from bot.rest import server
from bot.ts import Channel, TS3Facade, ThreadSafeTSConnection, create_connection, ignore_exception_handler, \
    signal_exception_handler

LOG = logging.getLogger(__name__)

# Global states
verify_channel: Optional[Channel] = None
http_server: Optional[HTTPServer] = None


def main():  #
    global verify_channel, http_server

    args = parse_args()
    LOG.info("Initializing script....")

    config = Config(args.config_path)
    database = get_or_create_database(config.db_file_name, config.current_version)
    ts_connection_pool: ConnectionPool[ThreadSafeTSConnection] = ConnectionPool(create=lambda: create_connection(config, config.bot_nickname),
                                                                                destroy_function=lambda conn: conn.close(),
                                                                                max_size=10, max_usage=1, idle=20, ttl=120)

    #######################################
    # Begins the connect to Teamspeak
    #######################################
    bot_loop_forever = True
    while bot_loop_forever:
        try:
            LOG.info("Connecting to Teamspeak server...")

            with ts_connection_pool.item() as main_ts3conn:
                ts_repository: TS3Facade = TS3Facade(main_ts3conn)
                bot_instance = Bot(database, ts_connection_pool, main_ts3conn, ts_repository, config)

                http_server = server.create_http_server(bot_instance, port=config.ipc_port)
                http_server.start()

                LOG.info("BOT loaded into server (%s) as %s (%s). Nickname '%s'", config.server_id, bot_instance.name, bot_instance.client_id, bot_instance.nickname)

                # Find the verify channel
                verify_channel = find_verify_channel(ts_repository, config.channel_name)

                # Move ourselves to the Verify chanel and register for text events
                move_to_channel(main_ts3conn, verify_channel, bot_instance.client_id, config.channel_name)

                main_ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="textchannel"))  # alert channel chat
                main_ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="textprivate"))  # alert Private chat
                main_ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="server"))

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
                while main_ts3conn.ts3exec(lambda tc: tc.is_connected(), signal_exception_handler)[0]:
                    # auditjob + keepalive check
                    schedule.run_pending()
                    event: TS3Response
                    try:
                        event, _ = main_ts3conn.ts3exec(lambda tc: tc.wait_for_event(timeout=config.bot_sleep_idle), ignore_exception_handler)
                        if event:
                            if "msg" in event.parsed[0]:
                                # text message
                                bot_instance.messageEventHandler(event)  # handle event
                            elif "reasonmsg" in event.parsed[0]:
                                # user left
                                pass
                            else:
                                bot_instance.loginEventHandler(event)
                    except Exception as ex:
                        LOG.error("Error while trying to handle event %s: %s", str(event), str(ex))

            LOG.warning("It appears the BOT has lost connection to teamspeak. Trying to restart connection in %s seconds....", config.bot_sleep_conn_lost)
            time.sleep(config.bot_sleep_conn_lost)

        except (ConnectionRefusedError, ts3.query.TS3TransportError):
            LOG.warning("Unable to reach teamspeak server..trying again in %s seconds...", config.bot_sleep_conn_lost)
            time.sleep(config.bot_sleep_conn_lost)
        except (KeyboardInterrupt, SystemExit):
            LOG.info("Stopping...")
            http_server.stop()
            sys.exit(0)


def parse_args():
    parser = argparse.ArgumentParser(description='ts-gw2-verifyBot')
    parser.add_argument('-c', '--config-path', dest='config_path', type=str, help='Config file location', default="./bot.conf")
    return parser.parse_args()


def move_to_channel(ts3conn, channel: Channel, client_id, channel_name):
    _, chnl_err = ts3conn.ts3exec(lambda tc: tc.exec_("clientmove", clid=client_id, cid=channel.channel_id))
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
