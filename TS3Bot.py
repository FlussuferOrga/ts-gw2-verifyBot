#!/usr/bin/python
import Config
import ts3 #teamspeak library
import time #time for sleep function
import re #regular expressions
import TS3Auth #includes datetime import
import sqlite3 #Database
import os #operating system commands -check if files exist
import datetime #for date strings
import schedule # Allows auditing of users every X days
from bot_messages import * #Import all Static messages the BOT may need
from threading import Thread, Lock, currentThread
import sys
import ipc
import traceback

#######################################
def default_exception_handler(ex):
    ''' prints the trace and returns the exception for further inspection '''
    traceback.print_exc()
    return ex

def ignore_exception_handler(ex):
    ''' acts as if no exception was raised, equivalent to except: pass'''
    return None 

def signal_exception_handler(ex):
    ''' returns the exception without printing it, useful for expected exceptions, signaling that an exception occurred '''
    return ex

#######################################
## Basic Classes
#######################################
class ThreadsafeTSConnection(object):
    RETRIES = 3

    @property
    def uri(self):
        return "telnet://%s:%s@%s:%s" % (self._user, self._password, self._host, str(self._port))

    def __init__(self, user, password, host, port, keepalive_interval = None, server_id = None, bot_nickname = None):
        '''
        Creates a new threadsafe TS3 connection.
        user: user to connect as
        password: password to connect to user with
        host: host of TS3 server
        port: port for server queries
        keepalive_interval: interval in which the keepalive is sent to the ts3 server
        server_id: the server id of the TS3 server we want to address, in case we have multiple.
                   Note that the server id HAS to be selected at some point, using the "use" command.
                   It has just been wrapped in here to allow for more convenient copying of the 
                   TS3 connection where the appropriate server is selected automatically.
        bot_nickname: nickname for the bot. Could be suffixed, see gentle_rename. If None is passed,
                      no naming will take place.
        '''
        self._user = user 
        self._password = password
        self._host = host 
        self._port = port
        self._keepalive_interval = int(keepalive_interval)
        self._server_id = server_id
        self._bot_nickname = bot_nickname
        self.lock = Lock()
        self.ts_connection = None # done in init()
        self.init()

    def init(self):
        if self.ts_connection is not None:
            try:
                self.ts_connection.close()
            except:
                pass # may already be closed, doesn't matter.
        self.ts_connection = ts3.query.TS3ServerConnection(self.uri) 
        if self._keepalive_interval is not None:
            schedule.cancel_job(self.keepalive) # to avoid accumulating keepalive calls during re-inits
            schedule.every(self._keepalive_interval).seconds.do(self.keepalive)
        if self._server_id is not None:
            self.ts3exec(lambda tc: tc.exec_("use", sid=self._server_id))
        if self._bot_nickname is not None:
            self.force_rename(self._bot_nickname)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def keepalive(self):
        self.ts_connection.send_keepalive()

    def ts3exec(self, handler, exception_handler = lambda ex: default_exception_handler(ex)): #eh = lambda ex: print(ex)):
        '''
        Excecutes a query() or exec_() on the internal TS3 connection.
        handler: a function ts3.query.TS3ServerConnection -> any
        exception_handler: a function Exception -> any. None will be interpreted as not having encountered an exception.
                           The default handler prints the stacktrace for the exception and returns the exception itself.
                           This changes the workflow of executing erroring code: instead of try-catching we need to 
                           decompose the tuple returned from this function and check if the exception result is anything
                           but None. E.g.:

                            try:
                               res = ts3con.query(...)
                            except Exception as ex:
                                # error handling

                           becomes

                            res,ex = threadsafe_ts3con.ts3exec(lambda tc: tc.query(...))
                            if ex:
                                # error handling

                           Note that the exception handler is only executed iff an exception is actually
                           being handled!

        returns a tuple with the results of the two handlers (result first, exception result second).
        '''
        with self.lock:
            failed = True
            fails = 0
            res = None
            exres = None
            while failed and fails < ThreadsafeTSConnection.RETRIES:
                failed = False
                try:
                    res = handler(self.ts_connection)
                except ts3.query.TS3TransportError:
                    failed = True
                    fails += 1
                    TS3Auth.log("Critical error on transport level! Attempt %s to restart the connection and send the command again." % (str(fails),))
                    self.init()
                except Exception as ex:
                    exres = exception_handler(ex)
        return (res, exres)

    def close(self):
        self.ts3exec(lambda tc: tc.close())

    def copy(self):
        tsc = ThreadsafeTSConnection(self._user, self._password, self._host, self._port, self._keepalive_interval, self._server_id, None)
        # make sure to 
        # 1. not pass bot_nickname to the constructor, or the child (copy) would call force_rename and attempt to kick the parent
        # 2. gently rename the copy afterwards
        tsc.gentle_rename(self._bot_nickname)
        return tsc

    def gentle_rename(self, nickname):
        '''
        Renames self to nickname, but attaches a running counter
        to the name if the nickname is already taken.
        '''
        i = 1
        new_nick = "%s(%d)" % (nickname,i)
        while not self.ts3exec(lambda tc: tc.query("clientfind", pattern=new_nick).first(), signal_exception_handler)[1]:
            i += 1
            new_nick = "%s(%d)" % (nickname,i)
        new_nick = "%s(%d)" % (nickname,i)
        self.ts3exec(lambda tc: tc.exec_("clientupdate", client_nickname=new_nick))
        self._bot_nickname = new_nick;   
        return self._bot_nickname  

    def force_rename(self, nickname):
        '''
        Attempts to forcefully rename self. 
        If the chosen nickname is already taken, the bot will attempt to kick that user.
        If that fails the bot will fall back to gentle renaming itself.
        '''
        imposter,free = self.ts3exec(lambda tc: tc.query("clientfind", pattern=nickname).first(), signal_exception_handler) # check if nickname is already in use
        if not free: # error occurs if no such user was found -> catching no exception means the name is taken
            _,ex = self.ts3exec(lambda tc: tc.exec_("clientkick", reasonid=5, reasonmsg="Reserved Nickname", clid=imposter.get("clid")), signal_exception_handler)
            if ex:
                TS3Auth.log("Renaming self to '%s' after kicking existing user with reserved name failed. Warning: this usually only happens for serverquery logins, meaning you are running multiple bots or you are having stale logins from crashed bot instances on your server. Only restarts can solve the latter." % (nickname,))
            else:
                TS3Auth.log("Kicked user who was using the reserved registration bot name '%s'." % (nickname,))                  
            nickname = self.gentle_rename(nickname)
            TS3Auth.log("Renamed self to '%s'." % (nickname,))               
        else:
            self.ts3exec(lambda tc: tc.exec_("clientupdate", client_nickname=nickname))
            TS3Auth.log("Forcefully renamed self to '%s'." % (nickname,))
        self._bot_nickname = nickname
        return self._bot_nickname

class Bot:
    @property
    def ts_connection(self):
        return self._ts_connection

    def __init__(self, db, ts_connection, verified_group, bot_nickname = "TS3BOT"):
        self._ts_connection = ts_connection
        admin_data, ex = self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("whoami").first())
        self.db_name = db
        self.name = admin_data.get('client_login_name')
        self.client_id = admin_data.get('client_id')
        self.nickname = self.ts_connection.force_rename(bot_nickname)
        self.verified_group = verified_group
        self.vgrp_id = self.groupFind(verified_group)
        self.getUserDatabase()
        self.c_audit_date = datetime.date.today() # Todays Date

    #Helps find the group ID for a group name
    def groupFind(self, group_to_find):
        self.groups_list, ex = self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("servergrouplist").all())
        for group in self.groups_list:
            if group.get('name') == group_to_find:
                return group.get('sgid')
        return -1

    def clientNeedsVerify(self, unique_client_id):
        client_db_id = self.getTsDatabaseID(unique_client_id)

        #Check if user is in verified group
        if any(perm_grp.get('name') == self.verified_group for perm_grp in self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("servergroupsbyclientid", cldbid = client_db_id).all())[0]):
            return False #User already verified

        #Check if user is authenticated in database and if so, re-adds them to the group
        current_entries = self.db_cursor.execute("SELECT * FROM users WHERE ts_db_id=?",  (unique_client_id,)).fetchall()
        if len(current_entries) > 0:
            self.setPermissions(unique_client_id)
            return False
        
        return True #User not verified

    def setPermissions(self, unique_client_id):
        try:
            client_db_id = self.getTsDatabaseID(unique_client_id)
            if Config.DEBUG:
                TS3Auth.log("Adding Permissions: CLUID [%s] SGID: %s   CLDBID: %s" % (unique_client_id, self.vgrp_id, client_db_id))
            #Add user to group
            _,ex = self.ts_connection.ts3exec(lambda ts_connection: ts_connection.exec_("servergroupaddclient", sgid = self.vgrp_id, cldbid = client_db_id))
            if ex:
                TS3Auth.log("Unable to add client to '%s' group. Does the group exist?" % self.verified_group)
        except ts3.query.TS3QueryError as err:
                TS3Auth.log("BOT [setPermissions]: Failed; %s" % err) #likely due to bad client id

    def removePermissions(self, unique_client_id):
        try:
            client_db_id = self.getTsDatabaseID(unique_client_id)
            if Config.DEBUG:
                TS3Auth.log("Removing Permissions: CLUID [%s] SGID: %s   CLDBID: %s" % (unique_client_id, self.vgrp_id, client_db_id))

            #Remove user from group
            _,ex = self.ts_connection.ts3exec(lambda ts_connection: ts_connection.exec_("servergroupdelclient", sgid = self.vgrp_id, cldbid = client_db_id), signal_exception_handler)
            if ex:
                TS3Auth.log("Unable to remove client from '%s' group. Does the group exist and are they member of the group?" % self.verified_group)
            #Remove users from all groups, except the whitelisted ones
            if Config.purge_completely:
                # FIXME: remove channel groups as well
                assigned_groups, ex = self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("servergroupsbyclientid", cldbid = client_db_id).all())
                for g in assigned_groups:
                    if g.get("name") not in Config.purge_whitelist:
                        self.ts_connection.ts3exec(lambda ts_connection: ts_connection.exec_("servergroupdelclient", sgid = g.get("sgid"), cldbid = client_db_id), lambda ex: None)
        except ts3.query.TS3QueryError as err:
            TS3Auth.log("BOT [removePermissions]: Failed; %s" %err) #likely due to bad client id

    def removePermissionsByGW2Account(self, gw2account):
        tsDbIds = self.db_cursor.execute("SELECT ts_db_id FROM users WHERE account_name = ?", (gw2account,)).fetchall()
        for tdi, in tsDbIds:
            self.removePermissions(tdi)
            TS3Auth.log("Removed permissions from %s" % (tdi,))
        self.db_cursor.execute("DELETE FROM users WHERE account_name = ?", (gw2account,))
        changes = self.db_cursor.execute("SELECT changes()").fetchone()[0];
        self.db_conn.commit()
        return changes

    def getUserDBEntry(self, client_unique_id):
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
            self.db_conn = sqlite3.connect(self.db_name, check_same_thread = False, detect_types = sqlite3.PARSE_DECLTYPES)
            self.db_cursor = self.db_conn.cursor()
            TS3Auth.log ("Loaded User Database...")
        else:
            self.db_conn = sqlite3.connect(self.db_name, check_same_thread = False, detect_types = sqlite3.PARSE_DECLTYPES)
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

    def TsClientLimitReached(self, gw_acct_name):
        current_entries = self.db_cursor.execute("SELECT * FROM users WHERE account_name=?",  (gw_acct_name, )).fetchall()
        return len(current_entries) >= Config.client_restriction_limit

    def addUserToDB(self, client_unique_id, account_name, api_key, created_date, last_audit_date):
        client_id = self.getActiveTsUserID(client_unique_id)
        client_exists = self.db_cursor.execute("SELECT * FROM users WHERE ts_db_id=?",  (client_unique_id,)).fetchall()
        if len(client_exists) > 1:
            TS3Auth.log('Function [addUserToDB] WARN: Found multipe database entries for single unique teamspeakid %s.' %client_unique_id, silent = True)
        if len(client_exists) != 0: # If client TS database id is in BOT's database.
            self.db_cursor.execute("""UPDATE users SET ts_db_id=?, account_name=?, api_key=?, created_date=?, last_audit_date=? WHERE ts_db_id=?""", (client_unique_id, account_name, api_key, created_date, last_audit_date, client_unique_id))
            TS3Auth.log("Teamspeak ID %s already in Database updating with new Account Name '%s'. (likely permissions changed by a Teamspeak Admin)" % (client_unique_id, account_name))
        else:
            self.db_cursor.execute("INSERT INTO users ( ts_db_id, account_name, api_key, created_date, last_audit_date) VALUES(?,?,?,?,?)",(client_unique_id, account_name, api_key, created_date, last_audit_date))
        self.db_conn.commit()

    def removeUserFromDB(self, client_db_id):
        #client_db_id=
        self.db_cursor.execute("DELETE FROM users WHERE ts_db_id=?", (client_db_id,))
        self.db_conn.commit()

    #def updateGuildTags(self, client_db_id, auth):
    def updateGuildTags(self, user, auth):
        if auth.guilds_error:
            TS3Auth.log("Did not update guild groups for player '%s', as loading the guild groups caused an error." % (auth.name,))
            return
        uid = user.unique_id # self.getTsUniqueID(client_db_id)
        client_db_id = user.ts_db_id
        ts_groups = {sg.get("name"):sg.get("sgid") for sg in self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("servergrouplist").all())[0]}
        ingame_member_of = set(auth.guild_names)
        # names of all groups the user is in, not just guild ones
        current_group_names = [g.get("name") for g in self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("servergroupsbyclientid", cldbid = client_db_id).all())[0]] 
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
                self.ts_connection.ts3exec(lambda ts_connection: ts_connection.exec_("servergroupdelclient", sgid = ts_groups[ggroup], cldbid = client_db_id))
            elif not gname in ingame_member_of:
                if ggroup not in ts_groups:
                    TS3Auth.log("Player %s should be removed from the TS group '%s' because they are not a member of guild '%s'. But no matching group exists. You should remove the entry for this guild from the db or check the spelling of the TS group in the DB. Skipping." % (ggroup, auth.name, gname))
                else:
                    TS3Auth.log("Player %s is no longer part of the guild '%s'. Removing attached group '%s'." % (auth.name, gname, ggroup))
                    self.ts_connection.ts3exec(lambda ts_connection: ts_connection.exec_("servergroupdelclient", sgid = ts_groups[ggroup], cldbid = client_db_id))

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
                            self.ts_connection.ts3exec(lambda ts_connection: ts_connection.exec_("servergroupaddclient", sgid = ts_groups[ts_group], cldbid = client_db_id))

    def auditUsers(self):
        self.c_audit_date = datetime.date.today() #Update current date everytime run
        self.db_audit_list = self.db_cursor.execute('SELECT * FROM users').fetchall()
        for audit_user in self.db_audit_list:

            #Convert to single variables
            audit_ts_id = audit_user[0]
            audit_account_name = audit_user[1]
            audit_api_key = audit_user[2]
            audit_created_date = audit_user[3]
            audit_last_audit_date = audit_user[4]

            if Config.DEBUG:
                print("Audit: User ",audit_account_name)
                print("TODAY |%s|  NEXT AUDIT |%s|" % (self.c_audit_date, audit_last_audit_date + datetime.timedelta(days = Config.audit_period)))

            #compare audit date
            if self.c_audit_date >= audit_last_audit_date + datetime.timedelta(days = Config.audit_period):
                TS3Auth.log ("User %s is due for auditing!" %audit_account_name)
                auth = TS3Auth.AuthRequest(audit_api_key, audit_account_name)
                if auth.success:
                    TS3Auth.log("User %s is still on %s. Succesful audit!" % (audit_account_name, auth.world.get('name')))
                    #self.getTsDatabaseID(audit_ts_id)
                    self.updateGuildTags(User(self.ts_connection, unique_id = audit_ts_id), auth)
                    #self.updateGuildTags(self.getTsDatabaseID(audit_ts_id), auth)
                    self.db_cursor.execute("UPDATE users SET last_audit_date = ? WHERE ts_db_id= ?", (self.c_audit_date, audit_ts_id,))
                    self.db_conn.commit()
                else:
                    TS3Auth.log("User %s is no longer on our server. Removing access...." % (audit_account_name))
                    self.removePermissions(audit_ts_id)
                    self.removeUserFromDB(audit_ts_id)

        self.db_cursor.execute('INSERT INTO bot_info (last_succesful_audit) VALUES (?)', (self.c_audit_date,))
        self.db_conn.commit()

    def broadcastMessage(self):
        self.ts_connection.ts3exec(lambda ts_connection: ts_connection.exec_("sendtextmessage", targetmode = 2, target = self._ts_connection._server_id, msg = Config.locale.get("bot_msg_broadcast")))

    def getActiveTsUserID(self, client_unique_id):
        return self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("clientgetids", cluid = client_unique_id).first().get('clid'))[0]

    def getTsDatabaseID(self, client_unique_id):
        return self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("clientgetdbidfromuid", cluid = client_unique_id).first().get('cldbid'))[0]

    def getTsUniqueID(self, client_db_id):
        return self.ts_connection.ts3exec(lambda ts_connection: ts_connection.query("clientgetnamefromdbid", cldbid = client_db_id).first().get('cluid'))[0]

    def login_event_handler(self, event):
        raw_sgroups = event.parsed[0].get('client_servergroups')
        raw_clid = event.parsed[0].get('clid')
        raw_cluid = event.parsed[0].get('client_unique_identifier')

        if raw_clid == self.client_id:
            return

        if self.clientNeedsVerify(raw_cluid):
            self.ts_connection.ts3exec(lambda ts_connection: ts_connection.exec_("sendtextmessage", targetmode = 1, target = raw_clid, msg = Config.locale.get("bot_msg_verify")),
                                        ignore_exception_handler) # error 516: invalid client type: another query-client logged in
                            

    def commandCheck(self, command_string):
        action=(None, None)
        for allowed_cmd in Config.cmd_list:
            if re.match('(^%s)\s*' % (allowed_cmd,), command_string):
                toks = command_string.split() # no argument for split() splits on arbitrary whitespace
                action = (toks[0], toks[1:])
        return action

    def try_get(self, dictionary, key, lower = False, typer = lambda x: x, default = None):
        v = typer(dictionary[key] if key in dictionary else default)
        return v.lower() if lower and isinstance(v, str) else v 

    def setresetroster(self, ts3conn, date, red = [], green = [], blue = [], ebg = []):
        leads = ([], red, green, blue, ebg) # keep RGB order! EBG as last! Pad first slot (header) with empty list

        channels = [(p,c.replace("$DATE", date)) for p,c in Config.reset_channels]
        for i in range(len(channels)):
            pattern, clean = channels[i]
            lead = leads[i]
            chan, ts3qe = ts3conn.ts3exec(lambda tsc: tsc.query("channelfind", pattern = pattern).first(), signal_exception_handler)
            if ts3qe is not None:
                if hasattr(ts3qe,"resp") and ts3qe.resp.error["id"] == "1281":
                    # empty result set
                    # no channel found for that pattern
                    TS3Auth.log("No channel found with pattern '%s'. Skipping." % (pattern,))
                else:
                    TS3Auth.log("Unexpected exception while trying to find a channel: %s" % (ts3qe,))
                    raise ts3qe
            else:
                newname = "%s%s" % (clean, ", ".join(lead))
                _, ts3qe = ts3conn.ts3exec(lambda tsc: tsc.exec_("channeledit", cid = chan.get("cid"), channel_name = newname), signal_exception_handler)                     
                if ts3qe is not None and ts3qe.resp.error["id"] == "771":
                    # channel name already in use
                    # probably not a bug (channel still unused), but can be a config problem
                    TS3Auth.log("Channel '%s' already exists. This is probably not a problem. Skipping." % (newname,))        

    def client_message_handler(self, ipcserver, clientsocket, message):
        mtype = self.try_get(message, "type", lower = True)
        mcommand = self.try_get(message, "command", lower = True)
        margs = self.try_get(message, "args", typer = lambda a: dict(a), default = {})
        mid = self.try_get(message, "message_id", typer = lambda a: int(a), default = -1)


        print("[%s] %s" % (mtype, mcommand))

        if mtype == "post":
            # POST commands
            if mcommand == "setresetroster":
                mdate = self.try_get(margs, "date", default = "dd.mm.yyyy")
                mred = self.try_get(margs, "rbl", default = [])
                mgreen = self.try_get(margs, "gbl", default = [])
                mblue = self.try_get(margs, "bbl", default = [])
                mebg = self.try_get(margs, "ebg", default = [])
                self.setresetroster(ipcserver.ts_connection, mdate, mred, mgreen, mblue, mebg)
        if mtype == "delete":
            # DELETE commands
            if mcommand == "user":
                mgw2account = self.try_get(margs,"gw2account", default = "")
                TS3Auth.log("Received request to delete user '%s' from the TS registration database." % (mgw2account,))
                changes = self.removePermissionsByGW2Account(mgw2account)
                clientsocket.respond(mid, mcommand, {"deleted": changes})

    # Handler that is used every time an event (message) is received from teamspeak server
    def message_event_handler(self, event):
        """
        *event* is a ts3.response.TS3Event instance, that contains the name
        of the event and the data.
        """
        if Config.DEBUG:
            print("\nEvent:")
            print("  event.event:", event.event)
            print("  event.parsed:", event.parsed)
            print("\n\n")

        raw_cmd = event.parsed[0].get('msg')
        rec_from_name = event.parsed[0].get('invokername').encode('utf-8') #fix any encoding issues introduced by Teamspeak
        rec_from_uid = event.parsed[0].get('invokeruid')
        rec_from_id = event.parsed[0].get('invokerid')
        rec_type = event.parsed[0].get('targetmode')

        if rec_from_id == self.client_id:
            return #ignore our own messages.
        try:
            # Type 2 means it was channel text
            if rec_type == "2":
                cmd, args = self.commandCheck(raw_cmd) #sanitize the commands but also restricts commands to a list of known allowed commands
                if cmd == "hideguild":
                    TS3Auth.log("User '%s' wants to hide guild '%s'." % (rec_from_name, args[0]))
                    try:
                        self.db_cursor.execute("INSERT INTO guild_ignores(guild_id, ts_db_id, ts_name) VALUES((SELECT guild_id FROM guilds WHERE ts_group = ?), ?,?)", (args[0], rec_from_uid, rec_from_name))
                        self.db_conn.commit()
                        TS3Auth.log("Success!")
                        self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_hide_guild_success")))
                    except sqlite3.IntegrityError:
                        self.db_conn.rollback()
                        TS3Auth.log("Failed. The group probably doesn't exist or the user is already hiding that group.")
                        self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_hide_guild_unknown")))

                elif cmd == "unhideguild":
                    TS3Auth.log("User '%s' wants to unhide guild '%s'." % (rec_from_name, args[0]))
                    self.db_cursor.execute("DELETE FROM guild_ignores WHERE guild_id = (SELECT guild_id FROM guilds WHERE ts_group = ? AND ts_db_id = ?)", (args[0], rec_from_uid))
                    changes = self.db_cursor.execute("SELECT changes()").fetchone()[0];
                    self.db_conn.commit()
                    if changes > 0:
                        TS3Auth.log("Success!")
                        self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_unhide_guild_success")))
                    else:
                        TS3Auth.log("Failed. Either the guild is unknown or the user had not hidden the guild anyway.")
                        self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_unhide_guild_unknown")))
                elif cmd == 'verifyme':
                    return # command disabled for now
                    if self.clientNeedsVerify(rec_from_uid):
                        TS3Auth.log("Verify Request Recieved from user '%s'. Sending PM now...\n        ...waiting for user response." %rec_from_name)
                        self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_verify")))
                    else:
                        TS3Auth.log("Verify Request Recieved from user '%s'. Already verified, notified user." %rec_from_name)
                        self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_alrdy_verified")))

            # Type 1 means it was a private message
            elif rec_type == '1':
                #reg_api_auth='\s*(\S+\s*\S+\.\d+)\s+(.*?-.*?-.*?-.*?-.*)\s*$'
                reg_api_auth='\s*(.*?-.*?-.*?-.*?-.*)\s*$'

                #Command for verifying authentication
                if re.match(reg_api_auth, raw_cmd):
                    pair = re.search(reg_api_auth, raw_cmd)
                    uapi = pair.group(1)

                    if self.clientNeedsVerify(rec_from_uid):
                        TS3Auth.log("Received verify response from %s" %rec_from_name)
                        auth = TS3Auth.AuthRequest(uapi)
                        
                        if Config.DEBUG:
                            TS3Auth.log('Name: |%s| API: |%s|' % (auth.name, uapi))

                        if auth.success:
                            limit_hit = self.TsClientLimitReached(auth.name)
                            if Config.DEBUG:
                                print("Limit hit check: %s" %limit_hit)
                            if not limit_hit:
                                TS3Auth.log("Setting permissions for %s as verified." %rec_from_name)

                                #set permissions
                                self.setPermissions(rec_from_uid)

                                #get todays date
                                today_date = datetime.date.today()

                                #Add user to database so we can query their API key over time to ensure they are still on our server
                                self.addUserToDB(rec_from_uid, auth.name, uapi, today_date, today_date)
                                self.updateGuildTags(User(self.ts_connection, unique_id = rec_from_uid), auth)
                                # self.updateGuildTags(rec_from_uid, auth)
                                TS3Auth.log("Added user to DB with ID %s" %rec_from_uid)

                                #notify user they are verified
                                self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_success")))
                            else:
                                # client limit is set and hit
                                self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_limit_Hit")))
                                TS3Auth.log("Received API Auth from %s, but %s has reached the client limit." % (rec_from_name, rec_from_name))
                        else:
                            #Auth Failed
                            self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_fail")))
                    else:
                        TS3Auth.log("Received API Auth from %s, but %s is already verified. Notified user as such." % (rec_from_name, rec_from_name))
                        self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_alrdy_verified")))
                else: 
                    self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_rcv_default")))
                    TS3Auth.log("Received bad response from %s [msg= %s]" % (rec_from_name, raw_cmd.encode('utf-8')))
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

class Channel(object):
    def __init__(self, ts_conn, channel_id):
        self.ts_conn = ts_conn
        self.channel_id = channel_id

#######################################

class User(object):
    '''
    Class that interfaces the Teamspeak-API with user-specific calls more convenient. 
    Since calls to the API are penalised, the class also tries to minimise those calls
    by only resolving properties when they are actually needed and then caching them (if sensible).
    '''
    def __init__(self, ts_conn, unique_id = None, ts_db_id = None, client_id = None):
        self.ts_conn = ts_conn
        self._unique_id = unique_id
        self._ts_db_id = ts_db_id
        self._client_id = client_id

        if all(x is None for x in [unique_id, ts_db_id, client_id]):
            raise Error("At least one ID must be non-null")      

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "User[unique_id: %s, ts_db_id: %s, client_id: %s]" % (self.unique_id, self.ts_db_id, self._client_id)

    @property
    def current_channel(self):
        entry = next((c for c in self.ts_conn.ts3exec(lambda t: t.query("clientlist").all())[0] if c.get("clid") == self.client_id), None)
        if entry:
            self._ts_db_id = entry.get("client_database_id") # since we are already retrieving this information...
        return Channel(self.ts_conn, entry.get("cid")) if entry else None

    @property
    def name(self):
        return self.ts_conn.ts3exec(lambda t: t.query("clientgetids", cluid = self.unique_id).first().get("name"))[0]

    @property
    def unique_id(self):
        if self._unique_id is None:
            if self._ts_db_id is not None:
                self._unique_id, ex = self.ts_conn.ts3exec(lambda t: t.query("clientgetnamefromdbid", cldbid = self._ts_db_id).first().get("cluid"))
            elif self._client_id is not None:
                ids, ex = self.ts_conn.ts3exec(lambda t: t.query("clientinfo", clid = self._client_id).first())
                self._unique_id = ids.get("client_unique_identifier")
                self._ts_db_id = ids.get("client_databased_id") # not required, but since we already queried it...
            else:
                raise Error("Unique ID can not be retrieved")
        return self._unique_id

    @property
    def ts_db_id(self):
        if self._ts_db_id is None:
            if self._unique_id is not None:
                self._ts_db_id, ex = self.ts_conn.ts3exec(lambda t: t.query("clientgetdbidfromuid", cluid = self._unique_id).first().get("cldbid"))
            elif self._client_id is not None:
                ids, ex = self.ts_conn.ts3exec(lambda t: t.query("clientinfo", clid = self._client_id).first())
                self._unique_id = ids.get("client_unique_identifier") # not required, but since we already queried it...
                self._ts_db_id = ids.get("client_database_id")
            else:
                raise Error("TS DB ID can not be retrieved")
        return self._ts_db_id

    @property
    def client_id(self):
        if self._client_id is None:
            if self._unique_id is not None:
                # easiest case: unique ID is set
                self._client_id, ex = self.ts_conn.ts3exec(lambda t: t.query("clientgetids", cluid = self._unique_id).first().get("clid"))
            elif self._ts_db_id is not None:
                self._unique_id, ex = self.ts_conn.ts3exec(lambda t: t.query("clientgetnamefromdbid", cldbid = self._ts_db_id).first().get("cluid"))
                self._client_id, ex = self.ts_conn.ts3exec(lambda t: t.query("clientgetids", cluid = self._unique_id).first().get("clid"))
            else:
                raise Error("Client ID can not be retrieved")
        return self._client_id  

#######################################

class CommanderChecker(Ticker):
    def __init__(self, ts3bot, ipcserver, commander_group_names, interval = 60):
        super(CommanderChecker, self).__init__(ts3bot, interval)
        self.commander_group_names = commander_group_names
        self.ipcserver = ipcserver

        cgroups = list(filter(lambda g: g.get("name") in commander_group_names, self.ts3bot.ts_connection.ts3exec(lambda t: t.query("channelgrouplist").all())[0]))
        if len(cgroups) < 1:
            TS3Auth.log("Could not find any group of %s to determine commanders by. Disabling this feature." % (str(commander_group_names),))
            self.commander_groups = []
            return

        self.commander_groups = [c.get("cgid") for c in cgroups]

    def execute(self):
        if not self.commander_groups:
            return # disabled if no groups were found

        active_commanders = []
        def retrieve_commanders(tsc):
            command = tsc.query("channelgroupclientlist")
            for cgid in self.commander_groups:
                command.pipe(cgid = cgid)
            return command.all()            

        acs, ts3qe = self.ts3bot.ts_connection.ts3exec(retrieve_commanders, signal_exception_handler)
        if ts3qe: # check for .resp, could by another exception type
            if ts3qe.resp is not None:
                if ts3qe.resp.error["id"] != "1281":
                    print(ts3qe.resp.error["id"])
                    print(type(ts3qe.resp.error["id"]))
                    print(ts3qe.resp.error["id"] == "1281")
                    # 1281 is "database empty result set", which is an expected error
                    # if not a single user currently wears a tag.
                    TS3Auth.log("Error while trying to resolve active commanders: %s." % (str(ts3qe),))
            else:
                print(ts3qe)
                print(ts3qe.resp)
                print(ts3qe.resp.error["id"])
                print(ts3qe.resp.error)
        else:
            active_commanders_entries = [(c, self.ts3bot.getUserDBEntry(self.ts3bot.getTsUniqueID(c.get("cldbid")))) for c in acs]
            for ts_entry, db_entry in active_commanders_entries:
                if db_entry is not None: # or else the user with the commander group was not registered and therefore not in the DB
                    u = User(self.ts3bot.ts_connection, ts_db_id = ts_entry.get("cldbid"))
                    if u.current_channel.channel_id == ts_entry.get("cid"):
                        # user could have the group in a channel but not be in there atm
                        ac = {}
                        ac["account_name"] = db_entry["account_name"]
                        ac["ts_cluid"] = db_entry["ts_db_id"]
                        ac["ts_display_name"], ex1 = self.ts3bot.ts_connection.ts3exec(lambda t: t.query("clientgetnamefromuid", cluid = db_entry["ts_db_id"]).first().get("name")) # no, there is probably no easier way to do this. I checked.
                        ac["ts_channel_name"], ex2 = self.ts3bot.ts_connection.ts3exec(lambda t: t.query("channelinfo", cid = ts_entry.get("cid")).first().get("channel_name"))
                        if ex1 or ex2:
                            TS3Auth.log("Could not determine information for commanding user with ID %s: '%s'. Skipping." % (str(ts_entry), ", ".join([str(e) for e in [ex1,ex2] if e is not None])))
                        else:
                            active_commanders.append(ac)
        # print({"commanders": active_commanders})
        self.ipcserver.broadcast({"commanders": active_commanders})

#######################################
