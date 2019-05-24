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

#######################################
#### Load Configs
#######################################

current_version='1.1'

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


# BOT Settings
bot_nickname = configs.get('bot settings','bot_nickname')
bot_sleep_conn_lost = int(configs.get('bot settings','bot_sleep_conn_lost'))
bot_sleep_idle = int(configs.get('bot settings','bot_sleep_idle'))
cmd_list = ast.literal_eval(configs.get('bot settings','cmd_list'))
db_file_name = configs.get('bot settings','db_file_name')
audit_period = int(configs.get('bot settings','audit_period')) #How long a single user can go without being audited
audit_interval = int(configs.get('bot settings','audit_interval')) # how often the BOT audits all users
client_restriction_limit= int(configs.get('bot settings','client_restriction_limit'))
timer_msg_broadcast = int(configs.get('bot settings','broadcast_message_timer'))
locale_setting = configs.get('bot settings','locale')

# Debugging (on or off) True/False
DEBUG = ast.literal_eval(configs.get('DEBUGGING','DEBUG'))

locale = getLocale(locale_setting)

#######################################

#######################################
## Basic Classes
#######################################

class Bot:
        def __init__(self,db,ts_connection):
                admin_data=ts_connection.whoami()
                self.db_name=db
                self.ts_connection=ts_connection
                self.name=admin_data[0].get('client_login_name')
                self.client_id=admin_data[0].get('client_id')
                self.nickname=bot_nickname
                self.vgrp_id=None
                self.groupFind(verified_group)
                self.getUserDatabase()
                self.c_audit_date=datetime.date.today() # Todays Date

        #Helps find the group ID for 'verified users group'
        def groupFind(self,group_to_find):
                self.groups_list=ts3conn.servergrouplist()
                for group in self.groups_list:
                        if group.get('name') == group_to_find:
                                self.vgrp_id=group.get('sgid')


        def clientNeedsVerify(self,unique_client_id):
                client_db_id = self.getTsDatabaseID(unique_client_id)

                #Check if user is in verified group
                if any(perm_grp.get('name') == verified_group for perm_grp in ts3conn.servergroupsbyclientid(cldbid=client_db_id)):
                        return False #User already verified

                #Check if user is authenticated in database and if so, re-adds them to the group
                current_entries=self.db_cursor.execute("SELECT * FROM users WHERE ts_db_id=?",  (unique_client_id,)).fetchall()
                if len(current_entries) > 0:
                        self.setPermissions(unique_client_id)
                        return False
                
                return True #User not verified

        def setPermissions(self,unique_client_id):
                try:
                        client_db_id = self.getTsDatabaseID(unique_client_id)
                        if DEBUG:
                                TS3Auth.log("Adding Permissions: CLUID [%s] SGID: %s   CLDBID: %s" %(unique_client_id, self.vgrp_id, client_db_id))
                        try:
                                #Add user to group
                                self.ts_connection.servergroupaddclient(sgid=self.vgrp_id, cldbid=client_db_id)
                        except:
                                TS3Auth.log("Unable to add client to '%s' group. Does the group exist?" %verified_group)
                except ts3.query.TS3QueryError as err:
                        TS3Auth.log("BOT [setPermissions]: Failed; %s" %err) #likely due to bad client id


        def removePermissions(self,unique_client_id):
                try:
                        client_db_id = self.getTsDatabaseID(unique_client_id)
                        if DEBUG:
                                TS3Auth.log("Removing Permissions: CLUID [%s] SGID: %s   CLDBID: %s" %(unique_client_id, self.vgrp_id, client_db_id))

                        #Remove user from group
                        try:
                                self.ts_connection.servergroupdelclient(sgid=self.vgrp_id, cldbid=client_db_id)
                        except:
                                TS3Auth.log("Unable to remove client from '%s' group. Does the group exist?" %verified_group)
                except ts3.query.TS3QueryError as err:
                        TS3Auth.log("BOT [removePermissions]: Failed; %s" %err) #likely due to bad client id

                        
        def getUserDatabase(self):
                if os.path.isfile(self.db_name):
                        self.db_conn = sqlite3.connect(self.db_name,check_same_thread=False,detect_types=sqlite3.PARSE_DECLTYPES)
                        self.db_cursor = self.db_conn.cursor()
                        TS3Auth.log ("Loaded User Database...")

                else:
                        self.db_conn = sqlite3.connect(self.db_name,check_same_thread=False,detect_types=sqlite3.PARSE_DECLTYPES)
                        self.db_cursor = self.db_conn.cursor()
                        TS3Auth.log("No User Database found...created new database!")
                        self.db_cursor.execute('''CREATE TABLE users
                                (ts_db_id text primary key, account_name text, api_key text, created_date date, last_audit_date date)''')
                        self.db_cursor.execute('''CREATE TABLE bot_info
                                (version text, last_succesful_audit date)''')
                        self.db_conn.commit()
                        self.db_cursor.execute('INSERT INTO bot_info (version, last_succesful_audit) VALUES (?,?)', (current_version, datetime.date.today(), ))
                        self.db_conn.commit()


        def TsClientLimitReached(self,gw_acct_name):
            limit_reached = False

            current_entries = self.db_cursor.execute("SELECT * FROM users WHERE account_name=?",  (gw_acct_name, )).fetchall()
            if len(current_entries) >= client_restriction_limit:
                limit_reached = True
            return limit_reached

        def addUserToDB(self,client_unique_id,account_name,api_key,created_date,last_audit_date):
            client_id=self.getActiveTsUserID(client_unique_id)
            client_exists=self.db_cursor.execute("SELECT * FROM users WHERE ts_db_id=?",  (client_unique_id,)).fetchall()
            if len(client_exists) > 1:
                TS3Auth.log('Function [addUserToDB] WARN: Found multipe database entries for single unique teamspeakid %s.' %client_unique_id, silent=True)
            if len(client_exists) != 0: # If client TS database id is in BOT's database.
                self.db_cursor.execute("""UPDATE users SET ts_db_id=?, account_name=?, api_key=?, created_date=?, last_audit_date=? WHERE ts_db_id=?""", (client_unique_id, account_name, api_key, created_date, last_audit_date,client_unique_id))
                TS3Auth.log("Teamspeak ID %s already in Database updating with new Account Name '%s'. (likely permissions changed by a Teamspeak Admin)" %(client_unique_id,account_name))
            else:
                self.db_cursor.execute("INSERT INTO users ( ts_db_id, account_name, api_key, created_date, last_audit_date) VALUES(?,?,?,?,?)",(client_unique_id, account_name, api_key, created_date, last_audit_date))
            self.db_conn.commit()


        def removeUserFromDB(self,client_db_id):
            #client_db_id=
            self.db_cursor.execute("DELETE FROM users WHERE ts_db_id=?", (client_db_id,))
            self.db_conn.commit()

        def auditUsers(self):
            self.c_audit_date=datetime.date.today() #Update current date everytime run
            self.db_audit_list=self.db_cursor.execute('SELECT * FROM users').fetchall()
            for audit_user in self.db_audit_list:

                #Convert to single variables
                audit_ts_id = audit_user[0]
                audit_account_name = audit_user[1]
                audit_api_key = audit_user[2]
                audit_created_date = audit_user[3]
                audit_last_audit_date = audit_user[4]

                if DEBUG:
                        print("Audit: User ",audit_account_name)
                        print("TODAY |%s|  NEXT AUDIT |%s|" %(self.c_audit_date,audit_last_audit_date + datetime.timedelta(days=audit_period)))

                #compare audit date

                if self.c_audit_date >= audit_last_audit_date + datetime.timedelta(days=audit_period):
                    TS3Auth.log ("User %s is due for audting!" %audit_account_name)
                    auth=TS3Auth.auth_request(audit_api_key,audit_account_name)
                    if auth.success:
                            TS3Auth.log("User %s is still on %s. Succesful audit!" %(audit_account_name,auth.world.get('name')))
                            self.db_cursor.execute("UPDATE users SET last_audit_date = ? WHERE ts_db_id= ?", (self.c_audit_date,audit_ts_id,))
                            self.db_conn.commit()
                    else:
                            TS3Auth.log("User %s is no longer on our server. Removing access...." %(audit_account_name))
                            self.removePermissions(audit_ts_id)
                            self.removeUserFromDB(audit_ts_id)

            self.db_cursor.execute('INSERT INTO bot_info (last_succesful_audit) VALUES (?)', (self.c_audit_date,))
            self.db_conn.commit()

        def broadcastMessage(self):
            self.ts_connection.sendtextmessage( targetmode=2,target=server_id, msg=locale.get("bot_msg_broadcast"))

        def getActiveTsUserID(self,client_unique_id):
            return self.ts_connection.clientgetids(cluid=client_unique_id)[0].get('clid')

        def getTsDatabaseID(self,client_unique_id):
            return self.ts_connection.clientgetdbidfromuid(cluid=client_unique_id)[0].get('cldbid')

        def getTsUniqueID(self,client_id):
            return self.ts_connection.clientgetuidfromclid(clid=client_id)[0].get('cldbid')
             
                


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



# Handler that is used every time an event (message) is received from teamspeak server
def my_event_handler(sender, event):
        """
        *sender* is the TS3Connection instance, that received the event.

        *event* is a ts3.response.TS3Event instance, that contains the name
        of the event and the data.
        """
        if DEBUG:
                print("\nEvent:")
                #print("  sender:", sender)
                print("  event.event:", event.event)
                print("  event.parsed:", event.parsed)
                print("\n\n")


        raw_cmd=event.parsed[0].get('msg')
        rec_from_name=event.parsed[0].get('invokername').encode('utf-8') #fix any encoding issues introdcued by Teamspeak
        rec_from_uid=event.parsed[0].get('invokeruid')
        rec_from_id=event.parsed[0].get('invokerid')
        rec_type=event.parsed[0].get('targetmode')

        if rec_from_uid == 'serveradmin':
                return #ignore any serveradmin messages, aka seeing our own messages.
        try:
                # Type 2 means it was channel text
                if rec_type == '2':
                        cmd=commandCheck(raw_cmd) #sanitize the commands but also restricts commands to a list of known allowed commands

                        #
                        if cmd == 'verifyme':
                                if BOT.clientNeedsVerify(rec_from_uid):
                                        TS3Auth.log("Verify Request Recieved from user '%s'. Sending PM now...\n        ...waiting for user response." %rec_from_name)
                                        sender.sendtextmessage( targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_verify"))
                                else:
                                        TS3Auth.log("Verify Request Recieved from user '%s'. Already verified, notified user." %rec_from_name)
                                        sender.sendtextmessage( targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_alrdy_verified"))


                # Type 1 means it was a private message
                elif rec_type == '1':
                    #reg_api_auth='\s*(\S+\s*\S+\.\d+)\s+(.*?-.*?-.*?-.*?-.*)\s*$'
                    reg_api_auth='\s*(.*?-.*?-.*?-.*?-.*)\s*$'


                    #Command for verifying authentication
                    if re.match(reg_api_auth,raw_cmd):
                        pair=re.search(reg_api_auth,raw_cmd)
                        uapi=pair.group(1)

                        if BOT.clientNeedsVerify(rec_from_uid):
                                
                                TS3Auth.log("Received verify response from %s" %rec_from_name)
                                auth=TS3Auth.auth_request(uapi)
                                
                                if DEBUG:
                                        TS3Auth.log('Name: |%s| API: |%s|' %(auth.name,uapi))
                                        
                                if auth.success:
                                        
                                        limit_hit=BOT.TsClientLimitReached(auth.name)
                                        if DEBUG:
                                            print("Limit hit check: %s" %limit_hit)
                                                
                                        if not limit_hit:
                                            TS3Auth.log("Setting permissions for %s as verified." %rec_from_name)

                                            #set permissions
                                            BOT.setPermissions(rec_from_uid)

                                            #get todays date
                                            today_date=datetime.date.today()

                                            #Add user to database so we can query their API key over time to ensure they are still on our server
                                            BOT.addUserToDB(rec_from_uid,auth.name,uapi,today_date,today_date)
                                            print ("Added user to DB with ID %s" %rec_from_uid)

                                            #notify user they are verified
                                            sender.sendtextmessage( targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_success"))
                                        else:
                                            # client limit is set and hit
                                            sender.sendtextmessage( targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_limit_Hit"))
                                            TS3Auth.log("Received API Auth from %s, but %s has reached the client limit." %(rec_from_name,rec_from_name))
                                
                                            
                                else:
                                        #Auth Failed
                                        sender.sendtextmessage( targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_fail"))
                        else:
                                TS3Auth.log("Received API Auth from %s, but %s is already verified. Notified user as such." %(rec_from_name,rec_from_name))
                                sender.sendtextmessage( targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_alrdy_verified"))
                                        
                        

                    else: 
                        sender.sendtextmessage( targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_rcv_default"))
                        TS3Auth.log("Received bad response from %s [msg= %s]" %(rec_from_name,raw_cmd.encode('utf-8')))
        except Exception as e:
                TS3Auth.log('BOT Event: Something went wrong during message received from teamspeak server. Likely bad user command/message.')
                TS3Auth.log(e)

                
        return None

#######################################


#######################################
# Begins the connect to Teamspeak
#######################################

bot_loop_forever=True
TS3Auth.log("Initializing script....")
while bot_loop_forever:
        try:
                TS3Auth.log("Connecting to Teamspeak server...")
                with ts3.query.TS3Connection(host,port) as ts3conn:

                    try:
                        ts3conn.login(client_login_name=user,client_login_password=passwd)

                    except ts3.query.TS3QueryError as err:
                        TS3Auth.log("Login Failed Reason: %s" %err.resp.error["msg"])
                        exit(1)
                    #Force connection to stay up by sending an alive message every 250 seconds
                    ts3conn.keepalive(interval=250)

                    #Choose which server instance we want to join (unless multiple exist the default of 1 should be fine)
                    ts3conn.use(sid=server_id)


                    #Define our bots info
                    BOT=Bot(db_file_name,ts3conn)
                    TS3Auth.log ("BOT loaded into server (%s) as %s (%s). Nickname '%s'" %(server_id,BOT.name,BOT.client_id,BOT.nickname))
                    ts3conn.clientupdate(client_nickname=BOT.nickname)

                    #Start our event handler (received the messages from server)
                    BOT.ts_connection.on_event.connect(my_event_handler)

                    # Find the verify channel
                    verify_channel_id=0
                    while verify_channel_id == 0:
                            try:
                                channel = ts3conn.channelfind(pattern=channel_name)
                                verify_channel_id=channel[0].get('cid')
                                channel_name=channel[0].get('channel_name')
                            except:
                                TS3Auth.log ("Unable to locate channel with name '%s'. Sleeping for 10 seconds..." %(channel_name))
                                time.sleep(10)


                    # Move ourselves to the Verify chanel and register for text events
                    try:
                            BOT.ts_connection.clientmove(clid=BOT.client_id,cid=verify_channel_id)
                            TS3Auth.log ("BOT has joined channel '%s' (%s)." %(channel_name,verify_channel_id))
                    except ts3.query.TS3QueryError as chnl_err: #BOT move failed because
                            TS3Auth.log("BOT Attempted to join channel '%s' (%s) WARN: %s" %(channel_name,verify_channel_id,chnl_err.resp.error["msg"]))
                            
                    BOT.ts_connection.servernotifyregister(event="textchannel") #alert channel chat
                    BOT.ts_connection.servernotifyregister(event="textprivate") #alert Private chat

                    

                    #Start looking for any received events from the server
                    BOT.ts_connection.recv_in_thread()

                    #Send message to the server that the BOT is up
                    BOT.ts_connection.sendtextmessage( targetmode=3,target=server_id, msg=locale.get("bot_msg",(bot_nickname,channel_name)))
                    TS3Auth.log("BOT is now registered to receive messages!")


                    TS3Auth.log("BOT Database Audit policies initiating.")
                    # Always audit users on initialize if user audit date is up (in case the script is reloaded several times before audit interval hits, so we can ensure we maintain user database accurately)
                    BOT.auditUsers()

                    #Set audit schedule job to run in X days
                    schedule.every(audit_interval).days.do(BOT.auditUsers)

                    #Set schedule to advertise broadcast message in channel
                    if timer_msg_broadcast > 0:
                            schedule.every(timer_msg_broadcast).seconds.do(BOT.broadcastMessage)
                    BOT.broadcastMessage() # Send initial message into channel


                    #Forces script to loop forever while we wait for events to come in, unless connection timed out. Then it should loop a new bot into creation.
                    TS3Auth.log("BOT now idle, waiting for requests.")
                    while BOT.ts_connection.is_connected():


                        #auditjob  check,
                        schedule.run_pending()
                        time.sleep(bot_sleep_idle)

                TS3Auth.log("It appears the BOT has lost connection to teamspeak. Trying to restart connection in %s seconds...." %bot_sleep_conn_lost)
                time.sleep(bot_sleep_conn_lost)

        except ConnectionRefusedError:
                TS3Auth.log("Unable to reach teamspeak server..trying again in %s seconds..." %bot_sleep_conn_lost)
                time.sleep(bot_sleep_conn_lost)


#######################################
