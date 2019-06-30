#!/usr/bin/python
import ts3 #teamspeak library
import time #time for sleep function
import re #regular expressions
import TS3Auth #includes datetime import
import sqlite3 #Database
import os #operating system commands -check if files exist
import datetime #for date strings
import configparser #parse in configuration
import ast #eval a string to a list/boolean (for cmd_list from 'bot settings' or DEBUG from config)
import schedule # Allows auditing of users every X days
from bot_messages import * #Import all Static messages the BOT may need
from TS3Bot import *
from threading import Thread
import sys
import ipc

#######################################
#### Load Configs
#######################################

current_version='1.2'

configs=configparser.ConfigParser()
configs.read('bot.conf')


# Teamspeak Connection Settings
host = configs.get('teamspeak connection settings','host')
port = configs.get('teamspeak connection settings','port')
user = configs.get('teamspeak connection settings','user')
passwd = configs.get('teamspeak connection settings','passwd')


# Teamspeak Other Settings
server_id = configs.get('teamspeak other settings','server_id')
channel_name = configs.get('teamspeak other settings','channel_name')
verified_group = configs.get('teamspeak other settings','verified_group')
verified_group_id = -1 # will be cached later

# BOT Settings
bot_nickname = configs.get('bot settings','bot_nickname')
bot_sleep_conn_lost = int(configs.get('bot settings','bot_sleep_conn_lost'))
# this setting is technically not required anymore. It just shouldn't exceed 5 minutes to avoid timeouts. 
# An appropriate user warning will be given.
bot_sleep_idle = int(configs.get('bot settings','bot_sleep_idle'))
cmd_list = ast.literal_eval(configs.get('bot settings','cmd_list'))
db_file_name = configs.get('bot settings','db_file_name')
audit_period = int(configs.get('bot settings','audit_period')) #How long a single user can go without being audited
audit_interval = int(configs.get('bot settings','audit_interval')) # how often the BOT audits all users
client_restriction_limit= int(configs.get('bot settings','client_restriction_limit'))
timer_msg_broadcast = int(configs.get('bot settings','broadcast_message_timer'))

ipc_port = int(configs.get('ipc settings','ipc_port'))

poll_group_name = configs.get('ipc settings','poll_group_name')
poll_group_poll_delay = int(configs.get('ipc settings','poll_group_poll_delay'))

purge_completely = False
try:
    purge_completely = ast.literal_eval(configs.get('bot settings','purge_completely'))
except configparser.NoOptionError:
    TS3Auth.log("No config setting 'purge_completely' found in the section [bot settings]. Please specify a boolean. Falling back to False.")

locale_setting = "EN"
try:
    locale_setting = configs.get('bot settings','locale')
except configparser.NoOptionError:
    TS3Auth.log("No config setting 'locale' found in the section [bot settings]. Please specify an available locale setting (ex. EN or DE). Falling back to English.")

purge_whitelist = ["Server Admin"]
try:
    purge_whitelist = ast.literal_eval(configs.get('bot settings','purge_whitelist'))
except configparser.NoOptionError:
    TS3Auth.log("No config setting 'purge_whitelist' found in the section [bot settings]. Falling back to 'Server Admin' group only.")

keepalive_interval = 60

# Debugging (on or off) True/False
DEBUG = ast.literal_eval(configs.get('DEBUGGING','DEBUG'))

locale = getLocale(locale_setting)

default_server_group_id = -1

if bot_sleep_idle > 300:
    TS3Auth.log("WARNING: setting bot_sleep_idle to a value higher than 300 seconds could result in timeouts!")

#######################################

#######################################
## Functions
#######################################

# Restricts commands for the channel messages (can add custom ones). Also add relevant code to 'rec_type 2' in my_event_handler.
def commandCheck(command_string):
    action=0
    for allowed_cmd in cmd_list:
        if re.match('(^%s)\s*' %allowed_cmd,command_string):
            action=allowed_cmd
    return action

#######################################

#######################################
# Begins the connect to Teamspeak
#######################################

bot_loop_forever=True
TS3Auth.log("Initializing script....")
while bot_loop_forever:
    try:    
        TS3Auth.log("Connecting to Teamspeak server...")
        with ts3.query.TS3ServerConnection("telnet://%s:%s@%s:%s" % (user, passwd, host, str(port))) as ts3conn:
            #ts3conn.exec_("login", client_login_name=user, client_login_password=passwd)

            #Choose which server instance we want to join (unless multiple exist the default of 1 should be fine)
            ts3conn.exec_("use", sid=server_id)

            #Define our bots info
            IPCS=ipc.Server(ipc_port)
            BOT=Bot(db_file_name,ts3conn)

            ipcthread = Thread(target = IPCS.run)
            ipcthread.daemon = True
            ipcthread.start()
            TS3Auth.log ("BOT loaded into server (%s) as %s (%s). Nickname '%s'" %(server_id,BOT.name,BOT.client_id,BOT.nickname))

            # What an absolute disaster of an API!
            # Instead of giving a None to signify that no
            # user with the specified username exists, a vacuous error
            # "invalid clientID", is thrown from clientfind.
            # So we have to catch exceptions to do control flow. 
            # Thanks for nothing.
            try:
                imposter = ts3conn.query("clientfind", pattern=BOT.nickname).first() # check if nickname is already in use
                if imposter:
                    try:
                        ts3conn.exec_("clientkick", reasonid=5, reasonmsg="Reserved Nickname", clid=imposter.get("clid"))
                        TS3Auth.log("Kicked user who was using the reserved registration bot name '%s'." % (BOT.nickname,))
                    except ts3.query.TS3QueryError as e:
                        i = 1
                        new_nick = "%s(%d)" % (BOT.nickname,i)
                        try:
                            while ts3conn.query("clientfind", pattern=new_nick).first():
                                i += 1
                                new_nick = "%s(%d)" % (BOT.nickname,i)
                        except ts3.query.TS3QueryError as e:
                            new_nick = "%s(%d)" % (BOT.nickname,i)
                            ts3conn.exec_("clientupdate", client_nickname=new_nick)
                            BOT.nickname = new_nick
                            TS3Auth.log("Renamed self to '%s' after kicking existing user with reserved name failed. Warning: this usually only happens for serverquery logins, meaning you are running multiple bots or you are having stale logins from crashed bot instances on your server. Only restarts can solve the latter." % (new_nick,))
            except ts3.query.TS3QueryError:
                ts3conn.exec_("clientupdate", client_nickname=BOT.nickname)

            # Find the verify channel
            verify_channel_id=0
            while verify_channel_id == 0:
                try:
                    channel = ts3conn.query("channelfind", pattern=channel_name).first()
                    verify_channel_id=channel.get('cid')
                    channel_name=channel.get('channel_name')
                except:
                    TS3Auth.log ("Unable to locate channel with name '%s'. Sleeping for 10 seconds..." %(channel_name))
                    time.sleep(10)

            # Find the verify group ID
            verified_group_id = BOT.groupFind(verified_group)

            # Find default server group
            default_server_group_id = ts3conn.query("serverinfo").first().get("virtualserver_default_server_group")

            # Move ourselves to the Verify chanel and register for text events
            try:
                ts3conn.exec_("clientmove", clid=BOT.client_id, cid=verify_channel_id)
                TS3Auth.log ("BOT has joined channel '%s' (%s)." %(channel_name,verify_channel_id))
            except ts3.query.TS3QueryError as chnl_err: #BOT move failed because
                TS3Auth.log("BOT Attempted to join channel '%s' (%s) WARN: %s" %(channel_name,verify_channel_id,chnl_err.resp.error["msg"]))
            
            ts3conn.exec_("servernotifyregister", event="textchannel") #alert channel chat
            ts3conn.exec_("servernotifyregister", event="textprivate") #alert Private chat
            ts3conn.exec_("servernotifyregister", event="server")

            #Send message to the server that the BOT is up
            # ts3conn.exec_("sendtextmessage", targetmode=3, target=server_id, msg=locale.get("bot_msg",(bot_nickname,)))
            TS3Auth.log("BOT is now registered to receive messages!")

            TS3Auth.log("BOT Database Audit policies initiating.")
            # Always audit users on initialize if user audit date is up (in case the script is reloaded several times before audit interval hits, so we can ensure we maintain user database accurately)
            BOT.auditUsers()

            #Set audit schedule job to run in X days
            schedule.every(audit_interval).days.do(BOT.auditUsers)

            #Since v2 of the ts3 library, keepalive must be sent manually to not screw with threads
            schedule.every(keepalive_interval).seconds.do(ts3conn.send_keepalive)

            CommanderChecker(BOT, IPCS, poll_group_name, poll_group_poll_delay)

            #Set schedule to advertise broadcast message in channel
            if timer_msg_broadcast > 0:
                    schedule.every(timer_msg_broadcast).seconds.do(BOT.broadcastMessage)
            BOT.broadcastMessage() # Send initial message into channel

            #Forces script to loop forever while we wait for events to come in, unless connection timed out. Then it should loop a new bot into creation.
            TS3Auth.log("BOT now idle, waiting for requests.")
            while ts3conn.is_connected():
                #auditjob + keepalive check
                schedule.run_pending()
                try:
                    event = ts3conn.wait_for_event(timeout=bot_sleep_idle)
                except ts3.query.TS3TimeoutError:
                    pass
                else:
                    try:
                        # print(vars(event))
                        if "msg" in event.parsed[0]:
                            # text message
                            BOT.message_event_handler(event) # handle event
                        elif "reasonmsg" in event.parsed[0]:
                            # user left
                            pass
                        else:
                            BOT.login_event_handler(event)
                    except Exception as ex:
                        TS3Auth.log("Error while trying to handle event %s: %s" % (str(event), str(ex)))

        TS3Auth.log("It appears the BOT has lost connection to teamspeak. Trying to restart connection in %s seconds...." %bot_sleep_conn_lost)
        time.sleep(bot_sleep_conn_lost)

    except (ConnectionRefusedError, ts3.query.TS3TransportError):
        TS3Auth.log("Unable to reach teamspeak server..trying again in %s seconds..." %bot_sleep_conn_lost)
        time.sleep(bot_sleep_conn_lost)
    except (KeyboardInterrupt, SystemExit):
        bot_loop_forever = False
        sys.exit(0)

#######################################
