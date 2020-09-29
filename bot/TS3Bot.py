#!/usr/bin/python
import datetime  # for date strings
import logging
import re
import sqlite3  # Database
import threading

import schedule
import time
import ts3
from ts3.query import TS3QueryError
from ts3.response import TS3Event

from bot.command_checker import CommanderChecker
from bot.config import Config
from bot.db import ThreadSafeDBConnection
from bot.ts import Channel, TS3Facade, User
from bot.util import StringShortener
from .TS3Auth import AuthRequest
from .audit_service import AuditService
from .connection_pool import ConnectionPool
from .guild_service import GuildService

# Queue Priorities, lower entries will be handles before, larger entries.
QUEUE_PRIORITY_AUDIT = 100
QUEUE_PRIORITY_JOIN = 20

LOG = logging.getLogger(__name__)


class Bot:

    def __init__(self, database: ThreadSafeDBConnection,
                 ts_connection_pool: ConnectionPool[TS3Facade],
                 ts_facade: TS3Facade,
                 config: Config):
        self._ts_facade = ts_facade  # use this only for representative Tasks such as sending messages to a user. Use a connection from the pool for worker tasks
        self._ts_connection_pool = ts_connection_pool  # worker connection pool
        self._config = config
        self._database_connection = database

        self.audit_service = AuditService(self._database_connection, self._ts_connection_pool, config, self)
        self.guild_service = GuildService(self._database_connection, self._ts_connection_pool, config)

        admin_data = self._ts_facade.whoami()
        self.name = admin_data.get('client_login_name')
        self.client_id = admin_data.get('client_id')

        self.nickname = self._ts_facade.force_rename(config.bot_nickname)

        self.verified_group = config.verified_group
        self.vgrp_id = self._find_group_by_name(self.verified_group)

        self.c_audit_date = datetime.date.today()
        self.commander_checker = CommanderChecker(self, config.poll_group_names)

    @property
    def ts_connection_pool(self):
        return self._ts_connection_pool

    # Helps find the group ID for a group name
    def _find_group_by_name(self, group_to_find):
        with self._ts_connection_pool.item() as ts_facade:
            self.groups_list = ts_facade.servergroup_list()
        for group in self.groups_list:
            if group.get('name') == group_to_find:
                return group.get('sgid')
        return -1

    def clientNeedsVerify(self, unique_client_id):
        with self._ts_connection_pool.item() as ts_facade:
            client_db_id = ts_facade.client_db_id_from_uid(unique_client_id)
            if client_db_id is None:
                raise ValueError("User not found in Teamspeak Database.")
            else:
                # Check if user is in verified group
                if any(perm_grp.get('name') == self.verified_group for perm_grp in ts_facade.servergroup_list_by_client(client_db_id)):
                    return False  # User already verified

        # Check if user is authenticated in database and if so, re-adds them to the group
        with self._database_connection.lock:
            current_entries = self._database_connection.cursor.execute("SELECT * FROM users WHERE ts_db_id=?", (unique_client_id,)).fetchall()
            if len(current_entries) > 0:
                self.setPermissions(unique_client_id)
                return False

        return True  # User not verified

    def setPermissions(self, unique_client_id):
        try:
            # Add user to group
            with self._ts_connection_pool.item() as facade:
                client_db_id = facade.client_db_id_from_uid(unique_client_id)
                if client_db_id is None:
                    LOG.warning("User not found in Database.")
                else:
                    LOG.debug("Adding Permissions: CLUID [%s] SGID: %s   CLDBID: %s", unique_client_id, self.vgrp_id, client_db_id)
                    ex = facade.servergroup_client_add(servergroup_id=self.vgrp_id, client_db_id=client_db_id)
                    if ex:
                        LOG.error("Unable to add client to '%s' group. Does the group exist?", self.verified_group)
        except ts3.query.TS3QueryError as err:
            LOG.error("Setting permissions failed: %s", err)  # likely due to bad client id

    def removePermissions(self, unique_client_id):
        try:
            with self._ts_connection_pool.item() as ts_facade:
                client_db_id = ts_facade.client_db_id_from_uid(unique_client_id)
                if client_db_id is None:
                    LOG.warning("User not found in Database.")
                else:
                    LOG.debug("Removing Permissions: CLUID [%s] SGID: %s   CLDBID: %s", unique_client_id, self.vgrp_id, client_db_id)

                    # Remove user from group
                    ex = ts_facade.servergroup_client_del(servergroup_id=self.vgrp_id, client_db_id=client_db_id)
                    if ex:
                        LOG.error("Unable to remove client from '%s' group. Does the group exist and are they member of the group?", self.verified_group)
                    # Remove users from all groups, except the whitelisted ones
                    if self._config.purge_completely:
                        # FIXME: remove channel groups as well
                        assigned_groups = ts_facade.servergroup_list_by_client(client_db_id)
                        if assigned_groups is not None:
                            for g in assigned_groups:
                                if g.get("name") not in self._config.purge_whitelist:
                                    ts_facade.servergroup_client_del(servergroup_id=g.get("sgid"), client_db_id=client_db_id)
        except TS3QueryError as err:
            LOG.error("Removing permissions failed: %s", err)  # likely due to bad client id

    def removePermissionsByGW2Account(self, gw2account):
        with self._database_connection.lock:
            tsDbIds = self._database_connection.cursor.execute("SELECT ts_db_id FROM users WHERE account_name = ?", (gw2account,)).fetchall()
            for tdi, in tsDbIds:
                self.removePermissions(tdi)
                LOG.debug("Removed permissions from %s", tdi)
            self._database_connection.cursor.execute("DELETE FROM users WHERE account_name = ?", (gw2account,))
            changes = self._database_connection.cursor.execute("SELECT changes()").fetchone()[0]
            self._database_connection.conn.commit()
            return changes

    def getUserDBEntry(self, client_unique_id):
        """
        Retrieves the DB entry for a unique client ID.
        Is either a dictionary of database-field-names to values, or None if no such entry was found in the DB.
        """
        with self._database_connection.lock:
            entry = self._database_connection.cursor.execute("SELECT * FROM users WHERE ts_db_id=?", (client_unique_id,)).fetchall()
            if len(entry) < 1:
                # user not registered
                return None
            entry = entry[0]
            keys = self._database_connection.cursor.description
            assert len(entry) == len(keys)
            return dict([(keys[i][0], entry[i]) for i in range(len(entry))])

    def TsClientLimitReached(self, gw_acct_name):
        with self._database_connection.lock:
            current_entries = self._database_connection.cursor.execute("SELECT * FROM users WHERE account_name=?", (gw_acct_name,)).fetchall()
            return len(current_entries) >= self._config.client_restriction_limit

    def addUserToDB(self, client_unique_id, account_name, api_key, created_date, last_audit_date):
        with self._database_connection.lock:
            # client_id = self.getActiveTsUserID(client_unique_id)
            client_exists = self._database_connection.cursor.execute("SELECT * FROM users WHERE ts_db_id=?", (client_unique_id,)).fetchall()
            if len(client_exists) > 1:
                LOG.warning("Found multiple database entries for single unique teamspeakid %s.", client_unique_id)
            if len(client_exists) != 0:  # If client TS database id is in BOT's database.
                self._database_connection.cursor.execute("""UPDATE users SET ts_db_id=?, account_name=?, api_key=?, created_date=?, last_audit_date=? WHERE ts_db_id=?""",
                                                         (client_unique_id, account_name, api_key, created_date, last_audit_date, client_unique_id))
                LOG.info("Teamspeak ID %s already in Database updating with new Account Name '%s'. (likely permissions changed by a Teamspeak Admin)", client_unique_id, account_name)
            else:
                self._database_connection.cursor.execute("INSERT INTO users ( ts_db_id, account_name, api_key, created_date, last_audit_date) VALUES(?,?,?,?,?)",
                                                         (client_unique_id, account_name, api_key, created_date, last_audit_date))
            self._database_connection.conn.commit()

    def removeUserFromDB(self, client_db_id):
        with self._database_connection.lock:
            self._database_connection.cursor.execute("DELETE FROM users WHERE ts_db_id=?", (client_db_id,))
            self._database_connection.conn.commit()

    # def updateGuildTags(self, client_db_id, auth):
    def updateGuildTags(self, ts_facade, user, auth):
        if auth.guilds_error:
            LOG.error("Did not update guild groups for player '%s', as loading the guild groups caused an error.", auth.name)
            return
        uid = user.unique_id  # self.getTsUniqueID(client_db_id)
        client_db_id = user.ts_db_id
        ts_groups = {sg.get("name"): sg.get("sgid") for sg in ts_facade.servergroup_list()}
        ingame_member_of = set(auth.guild_names)
        # names of all groups the user is in, not just guild ones
        current_group_names = []
        try:
            current_group_names = [g.get("name") for g in
                                   ts_facade.servergroup_list_by_client(client_db_id=client_db_id)]
        except TypeError:
            # user had no groups (results in None, instead of an empty list) -> just stick with the []
            pass

        # data of all guild groups the user is in
        param = ",".join(["'%s'" % (cgn.replace('"', '\\"').replace("'", "\\'"),) for cgn in current_group_names])
        # sanitisation is restricted to replacing single and double quotes. This should not be that much of a problem, since
        # the input for the parameters here are the names of our own server groups on our TS server.
        current_guild_groups = []
        hidden_groups = {}
        with self._database_connection.lock:
            current_guild_groups = self._database_connection.cursor.execute("SELECT ts_group, guild_name FROM guilds WHERE ts_group IN (%s)" % (param,)).fetchall()
            # groups the user doesn't want to wear
            hidden_groups = set(
                [g[0] for g in self._database_connection.cursor.execute("SELECT g.ts_group FROM guild_ignores AS gi JOIN guilds AS g ON gi.guild_id = g.guild_id  WHERE ts_db_id = ?", (uid,))])
        # REMOVE STALE GROUPS
        for ggroup, gname in current_guild_groups:
            if ggroup in hidden_groups:
                LOG.info("Player %s chose to hide group '%s', which is now removed.", auth.name, ggroup)
                ts_facade.servergroup_client_del(servergroup_id=ts_groups[ggroup], client_db_id=client_db_id)
            elif gname not in ingame_member_of:
                if ggroup not in ts_groups:
                    LOG.warning(
                        "Player %s should be removed from the TS group '%s' because they are not a member of guild '%s'."
                        " But no matching group exists."
                        " You should remove the entry for this guild from the db or check the spelling of the TS group in the DB. Skipping.",
                        ggroup, auth.name, gname)
                else:
                    LOG.info("Player %s is no longer part of the guild '%s'. Removing attached group '%s'.", auth.name, gname, ggroup)
                    ts_facade.servergroup_client_del(servergroup_id=ts_groups[ggroup], client_db_id=client_db_id)

        # ADD DUE GROUPS
        for g in ingame_member_of:
            ts_group = None
            with self._database_connection.lock:
                ts_group = self._database_connection.cursor.execute("SELECT ts_group FROM guilds WHERE guild_name = ?", (g,)).fetchone()
            if ts_group:
                ts_group = ts_group[0]  # first and only column, if a row exists
                if ts_group not in current_group_names:
                    if ts_group in hidden_groups:
                        LOG.info("Player %s is entitled to TS group '%s', but chose to hide it. Skipping.", auth.name, ts_group)
                    else:
                        if ts_group not in ts_groups:
                            LOG.warning(
                                "Player %s should be assigned the TS group '%s' because they are member of guild '%s'."
                                " But the group does not exist. You should remove the entry for this guild from the db or create the group."
                                " Skipping.",
                                auth.name, ts_group, g)
                        else:
                            LOG.info("Player %s is member of guild '%s' and will be assigned the TS group '%s'.", auth.name, g, ts_group)
                            ts_facade.servergroup_client_add(servergroup_id=ts_groups[ts_group], client_db_id=client_db_id)

    def trigger_user_audit(self):
        LOG.info("Auditing users")
        threading.Thread(name="FullAudit", target=self._audit_users, daemon=True).start()

    def _audit_users(self):
        self.c_audit_date = datetime.date.today()  # Update current date everytime run

        with self._database_connection.lock:
            db_audit_list = self._database_connection.cursor.execute('SELECT * FROM users').fetchall()
        for audit_user in db_audit_list:

            # Convert to single variables
            audit_ts_id = audit_user[0]
            audit_account_name = audit_user[1]
            audit_api_key = audit_user[2]
            # audit_created_date = audit_user[3]
            audit_last_audit_date = audit_user[4]

            LOG.debug("Audit: User %s", audit_account_name)
            LOG.debug("TODAY |%s|  NEXT AUDIT |%s|", self.c_audit_date, audit_last_audit_date + datetime.timedelta(days=self._config.audit_period))

            if self.c_audit_date >= audit_last_audit_date + datetime.timedelta(days=self._config.audit_period):  # compare audit date
                with self._ts_connection_pool.item() as ts_connection:
                    ts_uuid = ts_connection.client_db_id_from_uid(audit_ts_id)
                if ts_uuid is None:
                    LOG.info("User %s is not found in TS DB and could be deleted.", audit_account_name)
                    self._database_connection.cursor.execute("UPDATE users SET last_audit_date = ? WHERE ts_db_id= ?", ((datetime.date.today()), audit_ts_id,))
                    # self.removeUserFromDB(audit_ts_id)
                else:
                    LOG.info("User %s is due for auditing! Queueing", audit_account_name)
                    self.audit_service.queue_user_audit(QUEUE_PRIORITY_AUDIT, audit_account_name, audit_api_key, audit_ts_id)

        with self._database_connection.lock:
            self._database_connection.cursor.execute('INSERT INTO bot_info (last_succesful_audit) VALUES (?)', (self.c_audit_date,))
            self._database_connection.conn.commit()

    def audit_user_on_join(self, client_unique_id):
        db_entry = self.getUserDBEntry(client_unique_id)
        if db_entry is not None:
            account_name = db_entry["account_name"]
            api_key = db_entry["api_key"]
            self.audit_service.queue_user_audit(QUEUE_PRIORITY_JOIN, account_name=account_name, api_key=api_key, client_unique_id=client_unique_id)

    def _broadcast_message(self):
        broadcast_message = self._config.locale.get("bot_msg_broadcast")
        self._ts_facade.send_text_message_to_current_channel(msg=broadcast_message)

    def loginEventHandler(self, event_data):
        # raw_sgroups = event_data.get('client_servergroups')
        client_type: int = int(event_data.get('client_type'))
        raw_clid = event_data.get('clid')
        raw_cluid = event_data.get('client_unique_identifier')

        if client_type == 1:  # serverquery client, no need to send message or verify
            return

        if raw_clid == self.client_id:
            return

        if self.clientNeedsVerify(raw_cluid):
            self._ts_facade.send_text_message_to_client(raw_clid, self._config.locale.get("bot_msg_verify"))
        else:
            self.audit_user_on_join(raw_cluid)

    def commandCheck(self, command_string):
        action = (None, None)
        for allowed_cmd in self._config.cmd_list:
            if re.match(r'(^%s)\s*' % (allowed_cmd,), command_string):
                toks = command_string.split()  # no argument for split() splits on arbitrary whitespace
                action = (toks[0], toks[1:])
        return action

    def try_get(self, dictionary, key, lower=False, typer=lambda x: x, default=None):
        v = typer(dictionary[key] if key in dictionary else default)
        return v.lower() if lower and isinstance(v, str) else v

    def setResetroster(self, date, red=[], green=[], blue=[], ebg=[]):
        leads = ([], red, green, blue, ebg)  # keep RGB order! EBG as last! Pad first slot (header) with empty list

        with self._ts_connection_pool.item() as facade:
            channels = [(p, c.replace("$DATE", date)) for p, c in self._config.reset_channels]
            for i in range(len(channels)):
                pattern, clean = channels[i]
                lead = leads[i]

                TS3_MAX_SIZE_CHANNEL_NAME = 40
                shortened = StringShortener(TS3_MAX_SIZE_CHANNEL_NAME - len(clean)).shorten(lead)
                newname = "%s%s" % (clean, ", ".join(shortened))

                channel = facade.channel_find(pattern)
                if channel is None:
                    LOG.warning("No channel found with pattern '%s'. Skipping.", pattern)
                    return

                _, ts3qe = facade.channel_edit(channel_id=channel.channel_id, new_channel_name=newname)
                if ts3qe is not None and ts3qe.resp.error["id"] == "771":
                    # channel name already in use
                    # probably not a bug (channel still unused), but can be a config problem
                    LOG.info("Channel '%s' already exists. This is probably not a problem. Skipping.", newname)
        return 0

    def getActiveCommanders(self):
        return self.commander_checker.execute()

    #  def clientMessageHandler(self, clientsocket, message):
    #    mtype = self.try_get(message, "type", lower=True)
    #    mcommand = self.try_get(message, "command", lower=True)
    #    margs = self.try_get(message, "args", typer=lambda a: dict(a), default={})
    #    mid = self.try_get(message, "message_id", typer=lambda a: int(a), default=-1)

    #    LOG.debug("[%s] %s", mtype, mcommand)

    #    if mtype == "post":
    #        # POST commands
    #        if mcommand == "setresetroster":
    #            mdate = self.try_get(margs, "date", default="dd.mm.yyyy")
    #            mred = self.try_get(margs, "rbl", default=[])
    #            mgreen = self.try_get(margs, "gbl", default=[])
    #            mblue = self.try_get(margs, "bbl", default=[])
    #            mebg = self.try_get(margs, "ebg", default=[])
    #            self.setResetroster(mdate, mred, mgreen, mblue, mebg)
    #        if mcommand == "createguild":
    #            mname = self.try_get(margs, "name", default=None)
    #            mtag = self.try_get(margs, "tag", default=None)
    #            mgroupname = self.try_get(margs, "tsgroup", default=mtag)
    #            mcontacts = self.try_get(margs, "contacts", default=[])
    #            res = -1 if mname is None or mtag is None else self.createGuild(mname, mtag, mgroupname, mcontacts)
    #            clientsocket.respond(mid, mcommand, {"status": res})

    #    if mtype == "delete":
    #        # DELETE commands
    #        if mcommand == "user":
    #            mgw2account = self.try_get(margs, "gw2account", default="")
    #            LOG.info("Received request to delete user '%s' from the TS registration database.", mgw2account)
    #            changes = self.removePermissionsByGW2Account(mgw2account)
    #            clientsocket.respond(mid, mcommand, {"deleted": changes})
    #        if mcommand == "guild":
    #            mname = self.try_get(margs, "name", default=None)
    #            LOG.info("Received request to delete guild %s", mname)
    #            res = self.removeGuild(mname)
    #            print(res)
    #            clientsocket.respond(mid, mcommand, {"status": res})

    # Handler that is used every time an event (message) is received from teamspeak server
    def messageEventHandler(self, event_data):
        """
        *event* is a ts3.response.TS3Event instance, that contains the name
        of the event and the data.
        """
        raw_cmd = event_data.get('msg')
        rec_from_name = event_data.get('invokername').encode('utf-8')  # fix any encoding issues introduced by Teamspeak
        rec_from_uid = event_data.get('invokeruid')
        rec_from_id = event_data.get('invokerid')
        rec_type = event_data.get('targetmode')

        if rec_from_id == self.client_id:
            return  # ignore our own messages.
        try:
            # Type 2 means it was channel text
            if rec_type == "2":
                cmd, args = self.commandCheck(raw_cmd)  # sanitize the commands but also restricts commands to a list of known allowed commands
                if cmd == "ping":
                    LOG.info("Ping received from '%s'!", rec_from_name)
                    self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_pong_response"))
                if cmd == "hideguild":
                    LOG.info("User '%s' wants to hide guild '%s'.", rec_from_name, args[0])
                    with self._database_connection.lock:
                        try:
                            self._database_connection.cursor.execute("INSERT INTO guild_ignores(guild_id, ts_db_id, ts_name) VALUES((SELECT guild_id FROM guilds WHERE ts_group = ?), ?,?)",
                                                                     (args[0], rec_from_uid, rec_from_name))
                            self._database_connection.conn.commit()
                            LOG.debug("Success!")
                            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_hide_guild_success"))
                        except sqlite3.IntegrityError:
                            self._database_connection.conn.rollback()
                            LOG.debug("Failed. The group probably doesn't exist or the user is already hiding that group.")
                            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_hide_guild_unknown"))

                elif cmd == "unhideguild":
                    LOG.info("User '%s' wants to unhide guild '%s'.", rec_from_name, args[0])
                    with self._database_connection.lock:
                        self._database_connection.cursor.execute("DELETE FROM guild_ignores WHERE guild_id = (SELECT guild_id FROM guilds WHERE ts_group = ? AND ts_db_id = ?)",
                                                                 (args[0], rec_from_uid))
                        changes = self._database_connection.cursor.execute("SELECT changes()").fetchone()[0]
                        self._database_connection.conn.commit()
                        if changes > 0:
                            LOG.debug("Success!")
                            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_unhide_guild_success"))
                        else:
                            LOG.debug("Failed. Either the guild is unknown or the user had not hidden the guild anyway.")
                            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_unhide_guild_unknown"))
                elif cmd == 'verifyme':
                    return  # command disabled for now
                    # if self.clientNeedsVerify(rec_from_uid):
                    #     log.info("Verify Request Recieved from user '%s'. Sending PM now...\n        ...waiting for user response.", rec_from_name)
                    #     self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_verify")))
                    # else:
                    #     log.info("Verify Request Recieved from user '%s'. Already verified, notified user.", rec_from_name)
                    #     self.ts_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode = 1, target = rec_from_id, msg = Config.locale.get("bot_msg_alrdy_verified")))

            # Type 1 means it was a private message
            elif rec_type == '1':

                # reg_api_auth='\s*(\S+\s*\S+\.\d+)\s+(.*?-.*?-.*?-.*?-.*)\s*$'
                reg_api_auth = r'\s*(.*?-.*?-.*?-.*?-.*)\s*$'

                # Command for verifying authentication
                if re.match(reg_api_auth, raw_cmd):
                    pair = re.search(reg_api_auth, raw_cmd)
                    uapi = pair.group(1)

                    if self.clientNeedsVerify(rec_from_uid):
                        LOG.info("Received verify response from %s", rec_from_name)

                        auth = AuthRequest(uapi, self._config.required_servers, int(self._config.required_level))

                        LOG.debug('Name: |%s| API: |%s|', auth.name, uapi)

                        if auth.success:
                            limit_hit = self.TsClientLimitReached(auth.name)
                            if self._config.DEBUG:
                                LOG.debug("Limit hit check: %s", limit_hit)
                            if not limit_hit:
                                LOG.info("Setting permissions for %s as verified.", rec_from_name)

                                # set permissions
                                self.setPermissions(rec_from_uid)

                                # get todays date
                                today_date = datetime.date.today()

                                # Add user to database so we can query their API key over time to ensure they are still on our server
                                self.addUserToDB(rec_from_uid, auth.name, uapi, today_date, today_date)
                                self.updateGuildTags(self._ts_facade, User(self._ts_facade, unique_id=rec_from_uid), auth)
                                # self.updateGuildTags(rec_from_uid, auth)
                                LOG.debug("Added user to DB with ID %s", rec_from_uid)

                                # notify user they are verified
                                self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_msg_success"))
                            else:
                                # client limit is set and hit
                                self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_msg_limit_Hit"))
                                LOG.info("Received API Auth from %s, but %s has reached the client limit.", rec_from_name, rec_from_name)
                        else:
                            # Auth Failed
                            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_msg_fail"))
                    else:
                        LOG.debug("Received API Auth from %s, but %s is already verified. Notified user as such.", rec_from_name, rec_from_name)
                        self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_msg_alrdy_verified"))
                else:
                    self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_msg_rcv_default"))
                    LOG.info("Received bad response from %s [msg= %s]", rec_from_name, raw_cmd.encode('utf-8'))
                    # sys.exit(0)
        except Exception as ex:
            LOG.error("BOT Event: Something went wrong during message received from teamspeak server. Likely bad user command/message.", exc_info=ex)
        return None

    def listen_for_events(self):
        # Find the verify channel
        verify_channel = self._find_verify_channel()
        # Move ourselves to the Verify channel
        self._move_to_channel(verify_channel, self.client_id)
        # register for text events
        self._ts_facade.server_notify_register(["textchannel", "textprivate", "server"])

        LOG.info("BOT now online,sending broadcast.")
        self._broadcast_message()  # Send initial message into channel

        # Forces script to loop forever while we wait for events to come in, unless connection timed out or exception occurs.
        # Then it should loop a new bot into creation.
        LOG.info("BOT now idle, waiting for requests.")

        while self._ts_facade.is_connected():
            # auditjob trigger + keepalives
            schedule.run_pending()

            response: TS3Event = self._ts_facade.wait_for_event(timeout=self._config.bot_sleep_idle)
            if response is not None:
                event_type: str = response.event
                event_data = response.parsed[0]

                try:
                    self._handle_event(event_data, event_type)
                except Exception as ex:
                    LOG.error("Error while handling the event", exc_info=ex)

    def _handle_event(self, event_data, event_type):
        if event_type == 'notifytextmessage':  # text message
            if "msg" in event_data:
                self.messageEventHandler(event_data)  # handle event
        elif event_type == 'notifycliententerview':
            if event_data["client_type"] == '0':  # no server query client
                self.loginEventHandler(event_data)  # handle event
        elif event_type == 'notifyclientleftview':  # client left
            pass  # this event is not of interest
        else:
            LOG.warning("Unhandled Event: %s", event_type)

    def _move_to_channel(self, channel: Channel, client_id):
        chnl_err = self._ts_facade.client_move(client_id=client_id, channel_id=channel.channel_id)
        if chnl_err:
            LOG.warning("BOT Attempted to join channel '%s' (%s): %s", channel.channel_name, channel.channel_id, chnl_err.resp.error["msg"])
        else:
            LOG.info("BOT has joined channel '%s' (%s).", channel.channel_name, channel.channel_id)

    def _find_verify_channel(self):
        channel_name = self._config.channel_name

        found_channel = None
        while found_channel is None:
            found_channel = self._ts_facade.channel_find(channel_name)
            if found_channel is None:
                LOG.warning("Unable to locate channel with name '%s'. Sleeping for 10 seconds...", channel_name)
                time.sleep(10)
            else:
                return found_channel
