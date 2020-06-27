#!/usr/bin/python
import logging
import sys
import time  # time for sleep function
from typing import Optional

import schedule
import ts3
from ts3.response import TS3Response

from bot import Config, ipc
from bot.TS3Bot import Bot
from bot.ipc import HTTPServer
from bot.ts.TS3Facade import Channel, TS3Facade
from bot.ts.ThreadsafeTSConnection import ThreadsafeTSConnection, ignore_exception_handler, signal_exception_handler

LOG = logging.getLogger(__name__)

# Global states
BOT: Optional[Bot] = None
verify_channel: Optional[Channel] = None
http_server: Optional[HTTPServer] = None


def main(args):  #
    global BOT, verify_channel, http_server
    #######################################
    # Begins the connect to Teamspeak
    #######################################
    bot_loop_forever = True
    LOG.info("Initializing script....")
    while bot_loop_forever:
        try:
            LOG.info("Connecting to Teamspeak server...")
            with ThreadsafeTSConnection(Config.user,
                                        Config.passwd,
                                        Config.host,
                                        Config.port,
                                        Config.keepalive_interval,
                                        Config.server_id,
                                        Config.bot_nickname
                                        ) as ts3conn:
                ts_repository: TS3Facade = TS3Facade(ts3conn)
                BOT = Bot(Config.db_file_name, ts3conn, ts_repository, Config.verified_group, Config.bot_nickname)

                http_server = ipc.createHTTPServer(BOT, port=Config.ipc_port)
                http_server.start()

                LOG.info("BOT loaded into server (%s) as %s (%s). Nickname '%s'", Config.server_id, BOT.name, BOT.client_id, BOT.nickname)

                # Find the verify channel
                verify_channel = find_verify_channel(ts_repository)

                # Move ourselves to the Verify chanel and register for text events
                move_to_channel(ts3conn, verify_channel, BOT.client_id)

                ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="textchannel"))  # alert channel chat
                ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="textprivate"))  # alert Private chat
                ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="server"))

                # Send message to the server that the BOT is up
                # ts3conn.exec_("sendtextmessage", targetmode=3, target=server_id, msg=locale.get("bot_msg",(bot_nickname,)))
                LOG.info("BOT is now registered to receive messages!")

                LOG.info("BOT Database Audit policies initiating.")
                # Always audit users on initialize if user audit date is up (in case the script is reloaded several
                # times before audit interval hits, so we can ensure we maintain user database accurately)
                BOT.auditUsers()

                # Set audit schedule job to run in X days
                schedule.every(Config.audit_interval).days.do(BOT.auditUsers)

                # Since v2 of the ts3 library, keepalive must be sent manually to not screw with threads
                schedule.every(Config.keepalive_interval).seconds.do(lambda: ts3conn.ts3exec(lambda tc: tc.send_keepalive))

                LOG.info("BOT now online,sending broadcast.")
                BOT.broadcastMessage()  # Send initial message into channel

                # debug
                # BOT.setResetroster(ts3conn, "2020-04-01",
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
                while ts3conn.ts3exec(lambda tc: tc.is_connected(), signal_exception_handler)[0]:
                    # auditjob + keepalive check
                    schedule.run_pending()
                    event: TS3Response
                    try:
                        event, _ = ts3conn.ts3exec(lambda tc: tc.wait_for_event(timeout=Config.bot_sleep_idle), ignore_exception_handler)
                        if event:
                            if "msg" in event.parsed[0]:
                                # text message
                                BOT.messageEventHandler(event)  # handle event
                            elif "reasonmsg" in event.parsed[0]:
                                # user left
                                pass
                            else:
                                BOT.loginEventHandler(event)
                    except Exception as ex:
                        LOG.error("Error while trying to handle event %s: %s", str(event), str(ex))

            LOG.warning("It appears the BOT has lost connection to teamspeak. Trying to restart connection in %s seconds....", Config.bot_sleep_conn_lost)
            time.sleep(Config.bot_sleep_conn_lost)

        except (ConnectionRefusedError, ts3.query.TS3TransportError):
            LOG.warning("Unable to reach teamspeak server..trying again in %s seconds...", Config.bot_sleep_conn_lost)
            time.sleep(Config.bot_sleep_conn_lost)
        except (KeyboardInterrupt, SystemExit):
            LOG.info("Stopping...")
            http_server.stop()
            sys.exit(0)


def move_to_channel(ts3conn, channel: Channel, client_id):
    _, chnl_err = ts3conn.ts3exec(lambda tc: tc.exec_("clientmove", clid=client_id, cid=channel.channel_id))
    if chnl_err:
        LOG.warning("BOT Attempted to join channel '%s' (%s): %s", Config.channel_name, channel.channel_id, chnl_err.resp.error["msg"])
    else:
        LOG.info("BOT has joined channel '%s' (%s).", Config.channel_name, channel.channel_id)


def find_verify_channel(ts_repository):
    found_channel = None
    while found_channel is None:
        found_channel = ts_repository.channel_find(Config.channel_name)
        if found_channel is None:
            LOG.warning("Unable to locate channel with name '%s'. Sleeping for 10 seconds...", Config.channel_name)
            time.sleep(10)
        else:
            return found_channel

#######################################
