import logging

import binascii
import requests

import bot.gwapi as gw2api
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import ThreadSafeDBConnection
from bot.ts import TS3Facade, User

LOG = logging.getLogger(__name__)


def _handle_guild_icon(guild_id, name, ts3_facade):
    #########################################
    # RETRIEVE AND UPLOAD GUILD EMBLEM ICON #
    #########################################
    LOG.debug("Retrieving and uploading guild emblem as icon from gw2mists...")
    icon_url = f"https://emblem.werdes.net/emblem/{guild_id}/128"
    icon = requests.get(icon_url)

    # funnily enough, giving an invalid guild (or one that has no emblem)
    # results in HTTP 200, but a JSON explaining the error instead of an SVG image.
    # Storing this JSON and uploading it to TS just fails silently without
    # causing any problems!
    # Therefore checking content length..
    if len(icon.content) > 100:  # more than an "ok" or weird string
        icon_id = _generate_guild_icon_id(name)

        ts3_facade.upload_icon(icon_id, icon.content)
        return icon_id
    LOG.debug("Empty Response. Guild probably has no icon. Skipping Icon upload.")
    return None


def _generate_guild_icon_id(name) -> int:
    return binascii.crc32(name.encode('utf8'))


class GuildService:
    def __init__(self, database: ThreadSafeDBConnection, ts_connection_pool: ConnectionPool[TS3Facade], config: Config):
        self._database = database
        self.ts_connection_pool = ts_connection_pool
        self._config = config

    def create_guild(self, name, group_name, contacts):
        """
        Creates a guild in the TS.
        - retrieves and uploads their emblem as icon
        - creates guild channel with subchannels as read from the config with the icon
        - creates a guild group with the icon and appropriate permissions
        - adds in automatic assignment of the guild group upon re-verification
        - adds the contact persons as initial channel description
        - gives the contact role to the contact persons if they can be found in the DB

        name: name of the guild as is seen ingame
        groupname: group that should be used for them. Useful if the tag is already taken
        contacts: list of account names (Foo.1234) that should be noted down as contact and receive the special role for the new channel
        returns: 0 for success or an error code indicating the problem (see below)
        """
        SUCCESS = 0
        DUPLICATE_TS_GROUP = 1
        DUPLICATE_DB_ENTRY = 2
        DUPLICATE_TS_CHANNEL = 3
        MISSING_PARENT_CHANNEL = 4
        INVALID_PARAMETERS = 5

        if name is None or len(name) < 4:
            return INVALID_PARAMETERS

        if contacts is None or not isinstance(contacts, list):
            return INVALID_PARAMETERS

        if group_name is not None and len(group_name) < 2:
            return INVALID_PARAMETERS

        guild_info = gw2api.guild_get(gw2api.guild_search(name))
        if guild_info is None:
            return INVALID_PARAMETERS

        guild_name = guild_info.get("name")
        guild_tag = guild_info.get("tag")
        guild_id = guild_info.get("id")

        if group_name is None:
            group_name = guild_tag

        channel_name = self._build_channel_name(guild_info)
        channel_description = self._create_guild_channel_description(contacts, guild_id, guild_name, guild_tag)

        LOG.info("Creating guild '%s' with tag '%s', guild group '%s', and contacts '%s'.", guild_name, guild_tag, group_name, ", ".join(contacts))

        with self.ts_connection_pool.item() as ts_facade:
            # lock for the whole block to avoid constant interference
            # locking the ts3conn is vital to properly do the TS3FileTransfer
            # down the line.
            with self._database.lock:
                #############################################
                # CHECK IF GROUPS OR CHANNELS ALREADY EXIST #
                #############################################
                LOG.debug("Doing preliminary checks.")
                groups = ts_facade.servergroup_list()
                group = next((g for g in groups if g.get("name") == group_name), None)
                if group is not None:
                    # group already exists!
                    LOG.debug("Can not create a group '%s', because it already exists. Aborting guild creation.", group)
                    return DUPLICATE_TS_GROUP

                with self._database.lock:
                    dbgroups = self._database.cursor.execute("SELECT ts_group, guild_name FROM guilds WHERE ts_group = ?", (group_name,)).fetchall()
                    if len(dbgroups) > 0:
                        LOG.debug("Can not create a DB entry for TS group '%s', as it already exists. Aborting guild creation.", group_name)
                        return DUPLICATE_DB_ENTRY

                channel = ts_facade.channel_find(channel_name)
                if channel is not None:
                    # channel already exists!
                    LOG.debug("Can not create a channel '%s', as it already exists. Aborting guild creation.", channel_name)
                    return DUPLICATE_TS_CHANNEL

                parent = ts_facade.channel_find(self._config.guilds_parent_channel)
                if parent is None:
                    # parent channel does not exist!
                    LOG.debug("Can not find a parent-channel '%s' for guilds. Aborting guild creation.", self._config.guilds_parent_channel)
                    return MISSING_PARENT_CHANNEL

                LOG.debug("Checks complete.")

                # Icon uploading
                icon_id = _handle_guild_icon(guild_id, guild_name, ts_facade)  # Returns None if no icon

                ##################################
                # CREATE CHANNEL AND SUBCHANNELS #
                ##################################
                LOG.debug("Creating guild channels...")
                channel_list, _ = ts_facade.channel_list()

                # assert channel and group both exist and parent channel is available
                all_guild_channels = [c for c in channel_list if c.get("pid") == parent.channel_id]
                all_guild_channels.sort(key=lambda c: c.get("channel_name"), reverse=True)

                # Assuming the channels are already in order on the server,
                # find the first channel whose name is alphabetically smaller than the new channel name.
                # The sort_order of channels actually specifies after which channel they should be
                # inserted. Giving 0 as sort_order puts them in first place after the parent.
                found_place = False
                sort_order = 0
                i = 0
                while i < len(all_guild_channels) and not found_place:
                    if all_guild_channels[i].get("channel_name") > channel_name:
                        i += 1
                    else:
                        sort_order = int(all_guild_channels[i].get("cid"))
                        found_place = True

                cinfo, ex = ts_facade.channel_create(channel_name=channel_name,
                                                     channel_description=channel_description,
                                                     channel_parent_id=parent.channel_id,
                                                     channel_maxclients=0,
                                                     channel_order=sort_order)

                guild_channel_perms = [
                    ("i_channel_needed_join_power", 25),
                    ("i_channel_needed_subscribe_power", 25),
                    ("i_channel_needed_modify_power", 45),
                    ("i_channel_needed_delete_power", 75)
                ]

                perms = guild_channel_perms.copy()
                if icon_id is not None:
                    perms.append(("i_icon_id", icon_id))

                ts_facade.channel_add_permissions(cinfo.get("cid"), perms)

                for c in self._config.guild_sub_channels:
                    # FIXME: error check
                    sub_channel_info, ex = ts_facade.channel_create(channel_name=c, channel_parent_id=cinfo.get("cid"))
                    ts_facade.channel_add_permissions(sub_channel_info.get("cid"), guild_channel_perms)

            ###################
            # CREATE DB GROUP #
            ###################
            # must exist in DB before creating group to have it available when reordering groups.
            LOG.debug("Creating entry in database for auto assignment of guild group...")
            with self._database.lock:
                self._database.cursor.execute("INSERT INTO guilds(ts_group, guild_name) VALUES(?,?)", (group_name, guild_name))
                self._database.conn.commit()

            #######################
            # CREATE SERVER GROUP #
            #######################
            LOG.debug("Creating and configuring server group...")
            resp, ex = ts_facade.servergroup_add(group_name)
            if ex is not None and ex.resp.error["id"] == "1282":
                LOG.warning("Duplication error while trying to create the group '%s' for the guild %s [%s].", group_name, guild_name, guild_tag)

            guild_servergroup_id = resp.get("sgid")

            servergroup_permissions = self._create_guild_servergroup_permissions(icon_id)
            ts_facade.servergroup_add_permissions(guild_servergroup_id, servergroup_permissions)

            groups.append({"sgid": resp.get("sgid"), "name": group_name})  # the newly created group has to be added to properly iterate over the guild groups
            self._sort_guild_groups_using_talk_power(groups, ts_facade)

            ################
            # ADD CONTACTS #
            ################
            LOG.debug("Adding contacts...")
            cgroups, _ = ts_facade.channelgroup_list()
            contactgroup = next((cg for cg in cgroups if cg.get("name") == self._config.guild_contact_channel_group), None)
            if contactgroup is None:
                LOG.debug("Can not find a group for guild contacts. Skipping.")
            else:
                for c in contacts:
                    with self._database.lock:
                        accs = [row[0] for row in self._database.cursor.execute("SELECT ts_db_id FROM users WHERE lower(account_name) = lower(?)", (c,)).fetchall()]
                        for acc in accs:
                            try:
                                user = User(ts_facade, unique_id=acc)
                                user = User(ts_facade, unique_id=acc)
                                ex = ts_facade.set_client_channelgroup(channel_id=cinfo.get("cid"), channelgroup_id=contactgroup.get("cgid"), client_db_id=user.ts_db_id)
                                # while we are at it, add the contacts to the guild group as well
                                ts_facade.servergroup_client_add(servergroup_id=guild_servergroup_id, client_db_id=user.ts_db_id)

                                errored = ex is not None
                            except Exception:
                                errored = True
                            if errored:
                                LOG.error("Could not assign contact role '%s' to user '%s' with DB-unique-ID '%s' in "
                                          "guild channel for %s. Maybe the uid is not valid anymore.",
                                          self._config.guild_contact_channel_group, c, acc, guild_name)
            return SUCCESS

    def _create_guild_servergroup_permissions(self, icon_id):
        perms = [
            ("b_group_is_permanent", 1),
            ("i_group_show_name_in_tree", 1),
            ("i_group_needed_modify_power", 75),
            ("i_group_needed_member_add_power", 50),
            ("i_group_needed_member_remove_power", 50),
            ("i_group_sort_id", self._config.guilds_sort_id),
        ]
        if icon_id is not None:
            perms.append(("i_icon_id", icon_id))
        return perms

    def _sort_guild_groups_using_talk_power(self, groups, ts_facade):
        with self._database.lock:
            guildgroups = [g[0] for g in self._database.cursor.execute("SELECT ts_group FROM guilds ORDER BY ts_group").fetchall()]
        for i, guild_group in enumerate(guildgroups):
            g = next((g for g in groups if g.get("name") == guild_group), None)
            if g is None:
                # error! Group deleted from TS, but not from DB!
                LOG.warning("Found guild '%s' in the database, but no coresponding server group! Skipping this entry, but it should be fixed!", guildgroups[i])
            else:
                tp = self._config.guilds_maximum_talk_power - i

                if tp < 0:
                    LOG.warning("Talk power for guild %s is below 0.", g.get("name"))

                # sort guild groups to have users grouped by their guild tag alphabetically in channels
                _, _ = ts_facade.servergroup_add_permission(g.get("sgid"), "i_client_talk_power", tp)

    @staticmethod
    def _build_channel_name(guild_info) -> str:
        guild_name = guild_info.get("name")
        guild_tag = guild_info.get("tag")
        channel_name = "%s [%s]" % (guild_name, guild_tag)
        return channel_name

    @staticmethod
    def _create_guild_channel_description(contacts, id, name, tag):
        contacts = "\n".join(["    • %s" % c for c in contacts])
        text = (f"[center]\n"
                f"[img]https://emblem.werdes.net/emblem/{id}/128[/img]\n"
                f"[size=20]{name} - {tag}[/size]\n"
                f"[/center]\n"
                f"[hr]\n"
                f"[size=12]Contacts:[/size]\n"
                f"{contacts}\n"
                f"[hr]\n")
        return text

    def remove_guild(self, name):
        """
        Removes a guild from the TS. That is:
        - deletes their guild channel and all their subchannels by force
        - removes the group from TS by force
        - remove the auto-assignment for that group from the DB

        name: name of the guild as in the game
        """
        SUCCESS = 0
        INVALID_GUILD_NAME = 1
        NO_DB_ENTRY = 2
        INVALID_PARAMETERS = 5

        if name is None:
            return INVALID_PARAMETERS

        try:
            guild_info = gw2api.guild_get(gw2api.guild_search(name))
            if guild_info is None:
                return INVALID_GUILD_NAME
        except gw2api.ApiError as api_error:
            LOG.info("Error querying api for guild '%s'", name, exc_info=api_error)
            return INVALID_PARAMETERS

        guild_name = guild_info.get("name")

        with self._database.lock:
            g = self._database.cursor.execute("SELECT ts_group FROM guilds WHERE guild_name = ?", (guild_name,)).fetchone()
            groupname = g[0] if g is not None else None

        if groupname is None:
            return NO_DB_ENTRY

        # FROM DB
        LOG.debug("Deleting guild '%s' from DB.", guild_name)
        with self._database.lock:
            self._database.cursor.execute("DELETE FROM guilds WHERE guild_name = ?", (guild_name,))
            self._database.conn.commit()

        with self.ts_connection_pool.item() as ts3_facade:
            # CHANNEL
            channel_name = self._build_channel_name(guild_info)
            channel = ts3_facade.channel_find(channel_name)
            if channel is None:
                LOG.debug("No channel '%s' to delete.", channel_name)
            else:
                LOG.debug("Deleting channel '%s'.", channel_name)
                ts3_facade.channel_delete(channel.channel_id, force=True)

            # GROUP
            groups = ts3_facade.servergroup_list()
            group = next((g for g in groups if g.get("name") == groupname), None)
            if group is None:
                LOG.debug("No group '%s' to delete.", groupname)
            else:
                LOG.debug("Deleting group '%s'.", groupname)
                ts3_facade.servergroup_delete(group.get("sgid"), force=True)

            guild_icon_id = _generate_guild_icon_id(guild_name)

            ts3_facade.remove_icon_if_exists(guild_icon_id)

            return SUCCESS
