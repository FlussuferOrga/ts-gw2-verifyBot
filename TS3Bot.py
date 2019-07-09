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
from threading import Thread
import sys
import ipc
import traceback


#######################################
#### Load Configs
#######################################

current_version='1.2'

configs=configparser.ConfigParser()
configs.read('bot.conf')

cmd_list = ast.literal_eval(configs.get('bot settings','cmd_list'))

# Teamspeak Connection Settings
host = configs.get('teamspeak connection settings','host')
port = configs.get('teamspeak connection settings','port')
user = configs.get('teamspeak connection settings','user')
passwd = configs.get('teamspeak connection settings','passwd')


# Teamspeak Other Settings
server_id = configs.get('teamspeak other settings','server_id')
verified_group = configs.get('teamspeak other settings','verified_group')
verified_group_id = -1 # will be cached later

# BOT Settings
bot_nickname = configs.get('bot settings','bot_nickname')
# this setting is technically not required anymore. It just shouldn't exceed 5 minutes to avoid timeouts. 
# An appropriate user warning will be given.
bot_sleep_idle = int(configs.get('bot settings','bot_sleep_idle'))
audit_period = int(configs.get('bot settings','audit_period')) #How long a single user can go without being audited
client_restriction_limit= int(configs.get('bot settings','client_restriction_limit'))

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
## Basic Classes
#######################################
class Bot:
    def __init__(self,db,ts_connection):
        admin_data=ts_connection.query("whoami").first()
        self.db_name=db
        self.ts_connection=ts_connection
        self.name=admin_data.get('client_login_name')
        self.client_id=admin_data.get('client_id')
        self.nickname=bot_nickname
        self.vgrp_id = self.groupFind(verified_group)
        self.getUserDatabase()
        self.c_audit_date=datetime.date.today() # Todays Date

    #Helps find the group ID for a group name
    def groupFind(self,group_to_find):
        self.groups_list=self.ts_connection.query("servergrouplist").all()
        for group in self.groups_list:
            if group.get('name') == group_to_find:
                return group.get('sgid')
        return -1

    def clientNeedsVerify(self,unique_client_id):
        client_db_id = self.getTsDatabaseID(unique_client_id)

        #Check if user is in verified group
        if any(perm_grp.get('name') == verified_group for perm_grp in self.ts_connection.query("servergroupsbyclientid", cldbid=client_db_id).all()):
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
                self.ts_connection.exec_("servergroupaddclient", sgid=self.vgrp_id, cldbid=client_db_id)
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
                self.ts_connection.exec_("servergroupdelclient", sgid=self.vgrp_id, cldbid=client_db_id)
            except:
                TS3Auth.log("Unable to remove client from '%s' group. Does the group exist and are they member of the group?" %verified_group)
            #Remove users from all groups, except the whitelisted ones
            if purge_completely:
                assigned_groups = self.ts_connection.query("servergroupsbyclientid", cldbid=client_db_id).all()
                for g in assigned_groups:
                    if g.get("name") not in purge_whitelist:
                        try:
                            self.ts_connection.exec_("servergroupdelclient", sgid=g.get("sgid"), cldbid=client_db_id)
                        except:
                            pass
        except ts3.query.TS3QueryError as err:
            TS3Auth.log("BOT [removePermissions]: Failed; %s" %err) #likely due to bad client id

    def getUserDBEntry(self,client_unique_id):
        '''
        Retrieves the DB entry for a unique client ID.
        Is either a dictionary of database-field-names to values, or None if no such entry was found in the DB.
        '''
        entry = self.db_cursor.execute("SELECT * FROM users WHERE ts_db_id=?", (client_unique_id,)).fetchall()
        if len(entry) < 1:
            # user not registered
            return None
        entry = entry[0]
        keys = self.db_cursor.description
        assert len(entry) == len(keys)
        return dict([(keys[i][0], entry[i]) for i in range(len(entry))])
                    
    def getUserDatabase(self):
        if os.path.isfile(self.db_name):
            self.db_conn = sqlite3.connect(self.db_name,check_same_thread=False,detect_types=sqlite3.PARSE_DECLTYPES)
            self.db_cursor = self.db_conn.cursor()
            TS3Auth.log ("Loaded User Database...")
        else:
            self.db_conn = sqlite3.connect(self.db_name,check_same_thread=False,detect_types=sqlite3.PARSE_DECLTYPES)
            self.db_cursor = self.db_conn.cursor()
            TS3Auth.log("No User Database found...created new database!")
            # USERS
            self.db_cursor.execute('''CREATE TABLE users(ts_db_id text primary key, account_name text, api_key text, created_date date, last_audit_date date)''')
            # BOT INFO
            self.db_cursor.execute('''CREATE TABLE bot_info(version text, last_succesful_audit date)''')
            self.db_conn.commit()
            self.db_cursor.execute('INSERT INTO bot_info (version, last_succesful_audit) VALUES (?,?)', (current_version, datetime.date.today(), ))
            self.db_conn.commit()
            # GUILD INFO
            self.db_cursor.execute('''CREATE TABLE guilds(
                            guild_id integer primary key autoincrement, 
                            guild_name text UNIQUE,
                            ts_group text UNIQUE)''')
            self.db_conn.commit()

            # GUILD IGNORES
            self.db_cursor.execute('''CREATE TABLE guild_ignores(
                            guild_ignore_id integer primary key autoincrement,
                            guild_id integer,
                            ts_db_id text,
                            ts_name text,
                            FOREIGN KEY(guild_id) REFERENCES guilds(guild_id),
                            UNIQUE(guild_id, ts_db_id))''')
            self.db_conn.commit()

    def TsClientLimitReached(self,gw_acct_name):
        current_entries = self.db_cursor.execute("SELECT * FROM users WHERE account_name=?",  (gw_acct_name, )).fetchall()
        return len(current_entries) >= client_restriction_limit

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

    def updateGuildTags(self, client_db_id, auth):
        uid = self.getTsUniqueID(client_db_id)
        ts_groups = {sg.get("name"):sg.get("sgid") for sg in self.ts_connection.query("servergrouplist").all()}
        ingame_member_of = set(auth.guild_names)
        # names of all groups the user is in, not just guild ones
        current_group_names = [g.get("name") for g in self.ts_connection.query("servergroupsbyclientid", cldbid=client_db_id).all()] 
        # data of all guild groups the user is in
        param = ",".join(["'%s'" % (cgn.replace('"', '\\"').replace("'", "\\'"),) for cgn in current_group_names])
        # sanitisation is restricted to replacing single and double quotes. This should not be that much of a problem, since
        # the input for the parameters here are the names of our own server groups on our TS server.   
        current_guild_groups = self.db_cursor.execute("SELECT ts_group, guild_name FROM guilds WHERE ts_group IN (%s)" % (param,)).fetchall()
        # groups the user doesn't want to wear
        hidden_groups = set([g[0] for g in self.db_cursor.execute("SELECT g.ts_group FROM guild_ignores AS gi JOIN guilds AS g ON gi.guild_id = g.guild_id  WHERE ts_db_id = ?", (uid,))])
        # REMOVE STALE GROUPS
        for ggroup, gname in current_guild_groups:
            if ggroup in hidden_groups:
                TS3Auth.log("Player %s chose to hide group '%s', which is now removed." % (auth.name, ggroup))
                self.ts_connection.exec_("servergroupdelclient", sgid=ts_groups[ggroup], cldbid=client_db_id)
            elif not gname in ingame_member_of:
                if ggroup not in ts_groups:
                    TS3Auth.log("Player %s should be removed from the TS group '%s' because they are not a member of guild '%s'. But no matching group exists. You should remove the entry for this guild from the db or check the spelling of the TS group in the DB. Skipping." % (ggroup, auth.name, gname))
                else:
                    TS3Auth.log("Player %s is no longer part of the guild '%s'. Removing attached group '%s'." % (auth.name, gname, ggroup))
                    self.ts_connection.exec_("servergroupdelclient", sgid=ts_groups[ggroup], cldbid=client_db_id)

        # ADD DUE GROUPS
        for g in ingame_member_of:
            ts_group = self.db_cursor.execute("SELECT ts_group FROM guilds WHERE guild_name = ?", (g,)).fetchone()
            if ts_group:
                ts_group = ts_group[0] # first and only column, if a row exists
                if ts_group not in current_group_names:
                    if ts_group in hidden_groups:
                        TS3Auth.log("Player %s is entitled to TS group '%s', but chose to hide it. Skipping." % (auth.name, ts_group))
                    else:
                        if ts_group not in ts_groups:
                            TS3Auth.log("Player %s should be assigned the TS group '%s' because they are member of guild '%s'. But the group does not exist. You should remove the entry for this guild from the db or create the group. Skipping." % (auth.name, ts_group, g))
                        else:
                            TS3Auth.log("Player %s is member of guild '%s' and will be assigned the TS group '%s'." % (auth.name, g, ts_group))
                            self.ts_connection.exec_("servergroupaddclient", sgid = ts_groups[ts_group], cldbid=client_db_id)

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
                TS3Auth.log ("User %s is due for auditing!" %audit_account_name)
                auth=TS3Auth.auth_request(audit_api_key,audit_account_name)
                if auth.success:
                    TS3Auth.log("User %s is still on %s. Succesful audit!" %(audit_account_name,auth.world.get('name')))
                    self.getTsDatabaseID(audit_ts_id)
                    self.updateGuildTags(self.getTsDatabaseID(audit_ts_id), auth)
                    self.db_cursor.execute("UPDATE users SET last_audit_date = ? WHERE ts_db_id= ?", (self.c_audit_date,audit_ts_id,))
                    self.db_conn.commit()
                else:
                    TS3Auth.log("User %s is no longer on our server. Removing access...." %(audit_account_name))
                    self.removePermissions(audit_ts_id)
                    self.removeUserFromDB(audit_ts_id)

        self.db_cursor.execute('INSERT INTO bot_info (last_succesful_audit) VALUES (?)', (self.c_audit_date,))
        self.db_conn.commit()

    def broadcastMessage(self):
        self.ts_connection.exec_("sendtextmessage", targetmode=2,target=server_id, msg=locale.get("bot_msg_broadcast"))

    def getActiveTsUserID(self,client_unique_id):
        return self.ts_connection.query("clientgetids", cluid=client_unique_id).first().get('clid')

    def getTsDatabaseID(self,client_unique_id):
        return self.ts_connection.query("clientgetdbidfromuid", cluid=client_unique_id).first().get('cldbid')

    def getTsUniqueID(self,client_db_id):
        return self.ts_connection.query("clientgetnamefromdbid", cldbid=client_db_id).first().get('cluid')

    def login_event_handler(self, event):
        raw_sgroups = event.parsed[0].get('client_servergroups')
        raw_clid = event.parsed[0].get('clid')
        raw_cluid = event.parsed[0].get('client_unique_identifier')

        if raw_clid == self.client_id:
            return

        if self.clientNeedsVerify(raw_cluid):
            self.ts_connection.exec_("sendtextmessage", targetmode=1, target=raw_clid, msg=locale.get("bot_msg_verify"))

    def commandCheck(self, command_string):
        action=(None,None)
        for allowed_cmd in cmd_list:
            if re.match('(^%s)\s*' % (allowed_cmd,) ,command_string):
                toks = command_string.split() # no argument for split() splits on arbitrary whitespace
                action = (toks[0], toks[1:])
        return action

    # Handler that is used every time an event (message) is received from teamspeak server
    def message_event_handler(self, event):
        """
        *event* is a ts3.response.TS3Event instance, that contains the name
        of the event and the data.
        """
        if DEBUG:
            print("\nEvent:")
            print("  event.event:", event.event)
            print("  event.parsed:", event.parsed)
            print("\n\n")

        raw_cmd=event.parsed[0].get('msg')
        rec_from_name=event.parsed[0].get('invokername').encode('utf-8') #fix any encoding issues introduced by Teamspeak
        rec_from_uid=event.parsed[0].get('invokeruid')
        rec_from_id=event.parsed[0].get('invokerid')
        rec_type=event.parsed[0].get('targetmode')

        if rec_from_id == self.client_id:
            return #ignore our own messages.
        try:
            # Type 2 means it was channel text
            if rec_type == '2':
                cmd, args = self.commandCheck(raw_cmd) #sanitize the commands but also restricts commands to a list of known allowed commands
                if cmd == 'hideguild':
                    TS3Auth.log("User '%s' wants to hide guild '%s'." % (rec_from_name, args[0]))
                    try:
                        self.db_cursor.execute("INSERT INTO guild_ignores(guild_id, ts_db_id, ts_name) VALUES((SELECT guild_id FROM guilds WHERE ts_group = ?), ?,?)", (args[0], rec_from_uid, rec_from_name))
                        self.db_conn.commit()
                        TS3Auth.log("Success!")
                        self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_hide_guild_success"))
                    except sqlite3.IntegrityError:
                        self.db_conn.rollback()
                        TS3Auth.log("Failed. The group probably doesn't exist or the user is already part of the group.")
                        self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_hide_guild_unknown"))

                elif cmd == 'unhideguild':
                    TS3Auth.log("User '%s' wants to unhide guild '%s'." % (rec_from_name, args[0]))
                    self.db_cursor.execute("DELETE FROM guild_ignores WHERE guild_id = (SELECT guild_id FROM guilds WHERE ts_group = ? AND ts_db_id = ?)", (args[0], rec_from_uid))
                    changes = self.db_cursor.execute("SELECT changes()").fetchone()[0];
                    self.db_conn.commit()
                    if changes > 0:
                        TS3Auth.log("Success!")
                        self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_unhide_guild_success"))
                    else:
                        TS3Auth.log("Failed. Either the guild is unknown or the user had not hidden the guild anyway.")
                        self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_unhide_guild_unknown"))
                elif cmd == 'verifyme':
                    return # command disabled for now
                    if self.clientNeedsVerify(rec_from_uid):
                        TS3Auth.log("Verify Request Recieved from user '%s'. Sending PM now...\n        ...waiting for user response." %rec_from_name)
                        self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_verify"))
                    else:
                        TS3Auth.log("Verify Request Recieved from user '%s'. Already verified, notified user." %rec_from_name)
                        self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_alrdy_verified"))

            # Type 1 means it was a private message
            elif rec_type == '1':
                #reg_api_auth='\s*(\S+\s*\S+\.\d+)\s+(.*?-.*?-.*?-.*?-.*)\s*$'
                reg_api_auth='\s*(.*?-.*?-.*?-.*?-.*)\s*$'

                #Command for verifying authentication
                if re.match(reg_api_auth,raw_cmd):
                    pair=re.search(reg_api_auth,raw_cmd)
                    uapi=pair.group(1)

                    if self.clientNeedsVerify(rec_from_uid):
                        TS3Auth.log("Received verify response from %s" %rec_from_name)
                        auth=TS3Auth.auth_request(uapi)
                        
                        if DEBUG:
                            TS3Auth.log('Name: |%s| API: |%s|' %(auth.name,uapi))

                        if auth.success:
                            limit_hit=self.TsClientLimitReached(auth.name)
                            if DEBUG:
                                print("Limit hit check: %s" %limit_hit)
                            if not limit_hit:
                                TS3Auth.log("Setting permissions for %s as verified." %rec_from_name)

                                #set permissions
                                self.setPermissions(rec_from_uid)

                                #get todays date
                                today_date=datetime.date.today()

                                #Add user to database so we can query their API key over time to ensure they are still on our server
                                self.addUserToDB(rec_from_uid,auth.name,uapi,today_date,today_date)
                                self.updateGuildTags(rec_from_uid, auth)
                                TS3Auth.log("Added user to DB with ID %s" %rec_from_uid)

                                #notify user they are verified
                                self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_success"))
                            else:
                                # client limit is set and hit
                                self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_limit_Hit"))
                                TS3Auth.log("Received API Auth from %s, but %s has reached the client limit." %(rec_from_name,rec_from_name))
                        else:
                            pass
                            #Auth Failed
                            self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_fail"))
                    else:
                        TS3Auth.log("Received API Auth from %s, but %s is already verified. Notified user as such." %(rec_from_name,rec_from_name))
                        self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_alrdy_verified"))
                else: 
                    self.ts_connection.exec_("sendtextmessage", targetmode=1, target=rec_from_id, msg=locale.get("bot_msg_rcv_default"))
                    TS3Auth.log("Received bad response from %s [msg= %s]" %(rec_from_name,raw_cmd.encode('utf-8')))
                    # sys.exit(0)
        except Exception as e:
            TS3Auth.log('BOT Event: Something went wrong during message received from teamspeak server. Likely bad user command/message.')
            TS3Auth.log(e)
            TS3Auth.log(traceback.format_exc())
        return None

#######################################

class Ticker(object):
    '''
    Class that schedules events regularly and wraps the TS3Bot.
    '''
    def __init__(self, ts3bot, interval):
        self.ts3bot = ts3bot
        self.interval = interval
        schedule.every(interval).seconds.do(self.execute)

    def execute(self):
        pass

#######################################

class CommanderChecker(Ticker):
    def __init__(self, ts3bot, ipcserver, commander_group_name, interval = 60):
        super(CommanderChecker, self).__init__(ts3bot, interval)
        self.commander_group_name = commander_group_name
        self.ipcserver = ipcserver

        cgroups = list(filter(lambda g: g.get("name") == commander_group_name, self.ts3bot.ts_connection.query("channelgrouplist").all()))
        if len(cgroups) < 1:
            TS3Auth.log("Could not find a group called %s to determine commanders by. Disabling this feature." % (commander_group_name,))
            self.commander_group = -1
            return
        elif len(cgroups) > 1:
            TS3Auth.log("Found more than one group called %s, which is very weird. Using the first one, but preceed with caution." % (commander_group_name,))

        self.commander_group = cgroups[0].get("cgid")

    def execute(self):
        active_commanders = []
        try:
            active_commanders_entries = [self.ts3bot.getUserDBEntry(self.ts3bot.getTsUniqueID(c.get("cldbid"))) 
                                           for c in self.ts3bot.ts_connection.query("channelgroupclientlist", cgid=self.commander_group).all()]
            active_commanders = [c["account_name"] for c in active_commanders_entries if c is not None]
        except ts3.query.TS3QueryError:
            pass # empty result set, no users with that group
        self.ipcserver.broadcast({"commanders": active_commanders})

#######################################