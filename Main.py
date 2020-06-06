#!/usr/bin/python
import threading
from multiprocessing.context import Process

import ts3 #teamspeak library
import time #time for sleep function
import re #regular expressions
import TS3Auth #includes datetime import
import sqlite3 #Database
import os #operating system commands -check if files exist
import datetime #for date strings
import schedule # Allows auditing of users every X days
from bot_messages import * #Import all Static messages the BOT may need
from TS3Bot import *
from threading import Thread
import sys
import ipc
from bottle import Bottle, request, response
import Logger

def try_get(dictionary, key, lower = False, typer = lambda x: x, default = None):
    v = typer(dictionary[key] if key in dictionary else default)
    return v.lower() if lower and isinstance(v, str) else v 

log = Logger.getLogger()

#######################################
# Bottle
#######################################

app = Bottle()
app.route(path="/health",callback=lambda : "OK")  # health probe

@app.post("/resetroster")
def resetRoster():
    body = json.loads(request.body.read().decode("utf-8"))
    date = try_get(body, "date", default = "dd.mm.yyyy")
    red = try_get(body, "rbl", default = [])
    green = try_get(body, "gbl", default = [])
    blue = try_get(body, "bbl", default = [])
    ebg = try_get(body, "ebg", default = [])
    # BOT.setResetroster(ipcserver.ts_connection, date, red, green, blue, ebg)
    # FIXME: reply    
    # abort(code, message) or return {...}

@app.post("/guild")
def createGuild():
    body = json.loads(request.body.read().decode("utf-8"))
    name = try_get(body, "name", default = None)
    tag = try_get(body, "tag", default = None)
    groupname = try_get(body, "tsgroup", default = mtag)
    contacts = try_get(body, "contacts", default = [])
    #res = -1 if name is None or tag is None else self.createGuild(name, tag, groupname, contacts)
    #clientsocket.respond(mid, mcommand, {"status": res})       

@app.delete("/guild")
def deleteGuild():
    body = json.loads(request.body.read().decode("utf-8"))
    name = try_get(body, "name", default = None)
    # res = self.removeGuild(name)
    # clientsocket.respond(mid, mcommand, {"status": res})

@app.delete("/registration")
def deleteRegistration():
    body = json.loads(request.body.read().decode("utf-8"))
    gw2account = try_get(args,"gw2account", default = "")
    # changes = self.removePermissionsByGW2Account(mgw2account)
    # clientsocket.respond(mid, mcommand, {"deleted": changes})

httpPort = int(os.getenv('HTTP_PORT', 8080))
http_bind = os.getenv('HTTP_BIND', 'localhost')
t = threading.Thread(target=app.run, kwargs={'host': http_bind, 'port': httpPort})
t.daemon = True
t.start()

#######################################
# Begins the connect to Teamspeak
#######################################
default_server_group_id = -1

bot_loop_forever=True
log.info("Initializing script....")
while bot_loop_forever:
    try:
        log.info("Connecting to Teamspeak server...")
        with ThreadsafeTSConnection(Config.user
                                    , Config.passwd
                                    , Config.host
                                    , Config.port
                                    , Config.keepalive_interval
                                    , Config.server_id
                                    , Config.bot_nickname) as ts3conn:
            BOT=Bot(Config.db_file_name, ts3conn, Config.verified_group, Config.bot_nickname)

            ipcIsPublic = os.getenv("IPC_PUBLIC","false").lower() in ['true', '1', 'y', 'yes']
            if ipcIsPublic:
                log.warn("The IPC socket is open to the network, this is only ok in isolated and/or "
                            "secure environments")
            IPCS=ipc.TwistedServer(Config.ipc_port, ts3conn,
                                   client_message_handler = BOT.clientMessageHandler,
                                   local_only=not ipcIsPublic)
            ipcthread = Thread(target = IPCS.run)
            ipcthread.daemon = True
            ipcthread.start()
            log.info("BOT loaded into server (%s) as %s (%s). Nickname '%s'", Config.server_id, BOT.name, BOT.client_id, BOT.nickname)

            # Find the verify channel
            verify_channel_id=0
            while verify_channel_id == 0:
                channel, ex = ts3conn.ts3exec(lambda tc: tc.query("channelfind", pattern=Config.channel_name).first(), signal_exception_handler)
                if ex:
                    log.warn("Unable to locate channel with name '%s'. Sleeping for 10 seconds...", Config.channel_name)
                    time.sleep(10)
                else:
                    verify_channel_id=channel.get("cid")
                    channel_name=channel.get("channel_name")

            # Find the verify group ID
            verified_group_id = BOT.groupFind(Config.verified_group)

            # Find default server group
            default_server_group_id, ex = ts3conn.ts3exec(lambda tc: tc.query("serverinfo").first().get("virtualserver_default_server_group"))

            # Move ourselves to the Verify chanel and register for text events
            _, chnl_err = ts3conn.ts3exec(lambda tc: tc.exec_("clientmove", clid=BOT.client_id, cid=verify_channel_id))
            if chnl_err:
                log.warn("BOT Attempted to join channel '%s' (%s): %s", Config.channel_name, verify_channel_id, chnl_err.resp.error["msg"])
            else:
                log.info("BOT has joined channel '%s' (%s).", Config.channel_name, verify_channel_id)

            ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="textchannel")) #alert channel chat
            ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="textprivate")) #alert Private chat
            ts3conn.ts3exec(lambda tc: tc.exec_("servernotifyregister", event="server"))

            #Send message to the server that the BOT is up
            # ts3conn.exec_("sendtextmessage", targetmode=3, target=server_id, msg=locale.get("bot_msg",(bot_nickname,)))
            log.info("BOT is now registered to receive messages!")

            log.info("BOT Database Audit policies initiating.")
            # Always audit users on initialize if user audit date is up (in case the script is reloaded several times before audit interval hits, so we can ensure we maintain user database accurately)
            BOT.auditUsers()

            #Set audit schedule job to run in X days
            schedule.every(Config.audit_interval).days.do(BOT.auditUsers)

            #Since v2 of the ts3 library, keepalive must be sent manually to not screw with threads
            schedule.every(Config.keepalive_interval).seconds.do(lambda: ts3conn.ts3exec(lambda tc: tc.send_keepalive))

            commander_checker = CommanderChecker(BOT, IPCS, Config.poll_group_names, Config.poll_group_poll_delay)

            #Set schedule to advertise broadcast message in channel
            if Config.timer_msg_broadcast > 0:
                    schedule.every(Config.timer_msg_broadcast).seconds.do(BOT.broadcastMessage)
            BOT.broadcastMessage() # Send initial message into channel

            # debug
            """
            BOT.setResetroster(ts3conn, "2020-04-01", red = ["the name with the looooong name"], green = ["another really well hung name", "len", "oof. tat really a long one duuuude"], blue = ["[DUST] dude", "[DUST] anotherone", "[DUST] thecrusty dusty mucky man"], ebg = [])
            """
            testguilds = [("Unleash Chaos", "uC", "uC")
                        , ("Requiem of Execution", "RoE", "RoE")
                        , ("Zum Henker", "ZH", "ZH")
                        , ("Formation Wolke", "Zerg", "Zerg.")
                        , ("Zergs Rebellion", "Zerg", "Zerg")
                        , ("Flussufer Beach Boys", "FBB", "FBB")
                        , ("Ups Falsche Taste", "UPS", "UPS")
                        , ("Rising River", "Side", "Side")
                        , ("Demons of Dawn", "DoD", "DoD")]

            #for gname, gtag, ggroup in testguilds:
            #    BOT.removeGuild(gname, gtag, ggroup)
            #    BOT.createGuild(gname, gtag, ggroup, ["len.1879", "jey.1111"])

            #Forces script to loop forever while we wait for events to come in, unless connection timed out. Then it should loop a new bot into creation.
            log.info("BOT now idle, waiting for requests.")
            while ts3conn.ts3exec(lambda tc: tc.is_connected(), signal_exception_handler)[0]:
                #auditjob + keepalive check
                schedule.run_pending()
                event, ex = ts3conn.ts3exec(lambda tc: tc.wait_for_event(timeout=Config.bot_sleep_idle), ignore_exception_handler)
                if event:
                    try:
                        if "msg" in event.parsed[0]:
                            # text message
                            BOT.messageEventHandler(event) # handle event
                        elif "reasonmsg" in event.parsed[0]:
                            # user left
                            pass
                        else:
                            BOT.loginEventHandler(event)
                    except Exception as ex:
                        log.error("Error while trying to handle event %s: %s", str(event), str(ex))

        log.warning("It appears the BOT has lost connection to teamspeak. Trying to restart connection in %s seconds....", Config.bot_sleep_conn_lost)
        time.sleep(Config.bot_sleep_conn_lost)

    except (ConnectionRefusedError, ts3.query.TS3TransportError):
        log.warning("Unable to reach teamspeak server..trying again in %s seconds...", Config.bot_sleep_conn_lost)
        time.sleep(Config.bot_sleep_conn_lost)
    except (KeyboardInterrupt, SystemExit):
        bot_loop_forever = False
        app.close()
        sys.exit(0)

#######################################
