import logging

import ts3
from ts3.query import TS3QueryError

from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import ThreadSafeDBConnection
from bot.ts import TS3Facade

LOG = logging.getLogger(__name__)


class UserService:
    def __init__(self, database: ThreadSafeDBConnection, ts_connection_pool: ConnectionPool[TS3Facade], config: Config):
        self._database_connection = database
        self._ts_connection_pool = ts_connection_pool
        self._config = config

        self.verified_group = config.verified_group
        self.vgrp_id = self._find_group_by_name(self.verified_group)

    def remove_user_from_db(self, client_db_id):
        with self._database_connection.lock:
            self._database_connection.cursor.execute("DELETE FROM users WHERE ts_db_id=?", (client_db_id,))
            self._database_connection.conn.commit()

    def update_guild_tags(self, ts_facade, user, auth):
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

    def delete_registration(self, gw2account):
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
