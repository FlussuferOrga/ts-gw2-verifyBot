import logging
import os
import urllib

import binascii
import requests
import ts3
from ts3 import TS3Error
from ts3.filetransfer import TS3FileTransfer, TS3UploadError

import bot.gwapi as gw2api
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.db import ThreadSafeDBConnection
from bot.ts import TS3Facade, ThreadSafeTSConnection, User, default_exception_handler, signal_exception_handler

LOG = logging.getLogger(__name__)


def upload_icon(icon, icon_file_name, icon_server_path, ts3conn):
    def _ts_file_upload_hook(ts3_response: ts3.response.TS3QueryResponse):
        if ts3_response is not None:
            if ts3_response.parsed is not None and len(ts3_response.parsed) == 1 and ts3_response.parsed[0] is not None:
                if "msg" in ts3_response.parsed[0].keys() and ts3_response.parsed[0]["msg"] == "invalid size":
                    raise TS3UploadError(0, "The uploaded Icon is too large")

    with open(icon_file_name, "w+b") as file_handle:
        try:
            # svg
            file_handle.write(icon.content)
            file_handle.flush()
            file_handle.seek(0)

            # it is important to have acquired the lock for the ts3conn globally
            # at this point, as we directly pass the wrapped connection around
            upload = TS3FileTransfer(ts3conn.ts_connection)
            _ = upload.init_upload(input_file=file_handle,
                                   name=icon_server_path,
                                   cid=0,
                                   query_resp_hook=_ts_file_upload_hook)
            LOG.info(f"Icon {icon_file_name} uploaded as {icon_server_path}.")
        except TS3Error as ts3error:
            LOG.error("Error Uploading icon %s.", icon_file_name)
            LOG.error(ts3error)
        finally:
            file_handle.close()
            os.remove(icon_file_name)


def _handle_guild_icon(name, ts3conn):
    #########################################
    # RETRIEVE AND UPLOAD GUILD EMBLEM ICON #
    #########################################
    LOG.debug("Retrieving and uploading guild emblem as icon from gw2mists...")
    icon_url = "https://api.gw2mists.de/guilds/emblem/%s/50.svg" % (urllib.parse.quote(name),)
    icon = requests.get(icon_url)

    # funnily enough, giving an invalid guild (or one that has no emblem)
    # results in HTTP 200, but a JSON explaining the error instead of an SVG image.
    # Storing this JSON and uploading it to TS just fails silently without
    # causing any problems!
    # Therefore checking content length..
    if len(icon.content) > 0:
        icon_id = binascii.crc32(name.encode('utf8'))

        icon_local_file_name = "%s_icon.svg" % (urllib.parse.quote(name),)  # using name instead of tag, because tags are not unique
        icon_server_path = "/icon_%s" % (icon_id,)
        upload_icon(icon, icon_local_file_name, icon_server_path, ts3conn)
        return icon_id
    LOG.debug("Empty Response. Guild probably has no icon. Skipping Icon upload.")
    return None


class GuildService:
    def __init__(self, database: ThreadSafeDBConnection, ts_connection_pool: ConnectionPool[ThreadSafeTSConnection], config: Config):
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

        if group_name is None:
            group_name = guild_tag

        channel_name = self._build_channel_name(guild_info)
        channel_description = self._create_guild_channel_description(contacts, guild_name, guild_tag)

        LOG.info("Creating guild '%s' with tag '%s', guild group '%s', and contacts '%s'.", guild_name, guild_tag, group_name, ", ".join(contacts))

        with self.ts_connection_pool.item() as ts3conn:
            ts_facade = TS3Facade(ts3conn)
            # lock for the whole block to avoid constant interference
            # locking the ts3conn is vital to properly do the TS3FileTransfer
            # down the line.
            with ts3conn.lock, self._database.lock:
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
                icon_id = _handle_guild_icon(guild_name, ts3conn)  # Returns None if no icon

                ##################################
                # CREATE CHANNEL AND SUBCHANNELS #
                ##################################
                LOG.debug("Creating guild channels...")
                pid = parent.channel_id
                info, ex = ts3conn.ts3exec(lambda tsc: tsc.query("channelinfo", cid=pid).all(), signal_exception_handler)
                # assert channel and group both exist and parent channel is available
                all_guild_channels = [c for c in ts3conn.ts3exec(lambda tc: tc.query("channellist").all(), signal_exception_handler)[0] if c.get("pid") == pid]
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

                cinfo, ex = ts3conn.ts3exec(lambda tsc: tsc.query("channelcreate",
                                                                  channel_name=channel_name,
                                                                  channel_description=channel_description,
                                                                  cpid=pid,
                                                                  channel_flag_permanent=1,
                                                                  channel_maxclients=0,
                                                                  channel_order=sort_order,
                                                                  channel_flag_maxclients_unlimited=0)
                                            .first(), signal_exception_handler)

                guild_channel_perms = [
                    ("i_channel_needed_join_power", 25),
                    ("i_channel_needed_subscribe_power", 25),
                    ("i_channel_needed_modify_power", 45),
                    ("i_channel_needed_delete_power", 75)
                ]

                perms = guild_channel_perms.copy()
                if icon_id is not None:
                    perms.append(("i_icon_id", icon_id))

                def channel_apply_permissions(cid, perms):
                    for p, v in perms:
                        _, ex = ts3conn.ts3exec(lambda tsc: tsc.exec_("channeladdperm", cid=cid, permsid=p, permvalue=v, permnegated=0, permskip=0),
                                                signal_exception_handler)

                channel_apply_permissions(cinfo.get("cid"), perms)

                for c in self._config.guild_sub_channels:
                    # FIXME: error check
                    sub_channel_info, ex = ts3conn.ts3exec(lambda tsc: tsc.query("channelcreate", channel_name=c, cpid=cinfo.get("cid"), channel_flag_permanent=1)
                                                           .first(), signal_exception_handler)
                    channel_apply_permissions(sub_channel_info.get("cid"), guild_channel_perms)

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
            resp, ex = ts3conn.ts3exec(lambda tsc: tsc.query("servergroupadd", name=group_name).first(), signal_exception_handler)
            guildgroupid = resp.get("sgid")
            if ex is not None and ex.resp.error["id"] == "1282":
                LOG.warning("Duplication error while trying to create the group '%s' for the guild %s [%s].", group_name, guild_name, guild_tag)

            def servergroupaddperm(sgid, permsid, permvalue):
                return ts3conn.ts3exec(lambda tsc: tsc.exec_("servergroupaddperm",
                                                             sgid=sgid,
                                                             permsid=permsid,
                                                             permvalue=permvalue,
                                                             permnegated=0,
                                                             permskip=0),
                                       signal_exception_handler)

            perms = self._create_guild_channel_permissions(icon_id, perms)

            for p, v in perms:
                _, _ = servergroupaddperm(guildgroupid, p, v)

            groups.append({"sgid": resp.get("sgid"), "name": group_name})  # the newly created group has to be added to properly iterate over the guild groups
            self._sort_guild_groups_using_talk_power(groups, servergroupaddperm)

            ################
            # ADD CONTACTS #
            ################
            LOG.debug("Adding contacts...")
            cgroups, ex = ts3conn.ts3exec(lambda tsc: tsc.query("channelgrouplist").all(), default_exception_handler)
            contactgroup = next((cg for cg in cgroups if cg.get("name") == self._config.guild_contact_channel_group), None)
            if contactgroup is None:
                LOG.debug("Can not find a group for guild contacts. Skipping.")
            else:
                for c in contacts:
                    with self._database.lock:
                        accs = [row[0] for row in self._database.cursor.execute("SELECT ts_db_id FROM users WHERE lower(account_name) = lower(?)", (c,)).fetchall()]
                        for acc in accs:
                            try:
                                user = User(ts3conn, unique_id=acc, ex_hand=signal_exception_handler)
                                _, ex = ts3conn.ts3exec(lambda tsc: tsc.exec_("setclientchannelgroup", cid=cinfo.get("cid"), cldbid=user.ts_db_id, cgid=contactgroup.get("cgid")),
                                                        signal_exception_handler)
                                # while we are at it, add the contacts to the guild group as well
                                _, ex2 = ts3conn.ts3exec(lambda tsc: tsc.exec_("servergroupaddclient", sgid=guildgroupid, cldbid=user.ts_db_id), signal_exception_handler)

                                errored = ex is not None
                            except Exception:
                                errored = True
                            if errored:
                                LOG.error("Could not assign contact role '%s' to user '%s' with DB-unique-ID '%s' in "
                                          "guild channel for %s. Maybe the uid is not valid anymore.",
                                          self._config.guild_contact_channel_group, c, acc, guild_name)
            return SUCCESS

    def _create_guild_channel_permissions(self, icon_id, perms):
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

    def _sort_guild_groups_using_talk_power(self, groups, servergroupaddperm):
        with self._database.lock:
            guildgroups = [g[0] for g in self._database.cursor.execute("SELECT ts_group FROM guilds ORDER BY ts_group").fetchall()]
        for i in range(len(guildgroups)):
            g = next((g for g in groups if g.get("name") == guildgroups[i]), None)
            if g is None:
                # error! Group deleted from TS, but not from DB!
                LOG.warning("Found guild '%s' in the database, but no coresponding server group! Skipping this entry, but it should be fixed!", guildgroups[i])
            else:
                tp = self._config.guilds_maximum_talk_power - i

                if tp < 0:
                    LOG.warning("Talk power for guild %s is below 0.", g.get("name"))

                # sort guild groups to have users grouped by their guild tag alphabetically in channels
                _, _ = servergroupaddperm(g.get("sgid"), "i_client_talk_power", tp)

    @staticmethod
    def _build_channel_name(guild_info) -> str:
        guild_name = guild_info.get("name")
        guild_tag = guild_info.get("tag")
        channel_name = "%s [%s]" % (guild_name, guild_tag)
        return channel_name

    @staticmethod
    def _create_guild_channel_description(contacts, name, tag):
        contacts = "\n".join(["    • %s" % c for c in contacts])
        text = (f"[center]\n"
                f"[img]https://api.gw2mists.de/guilds/emblem/{urllib.parse.quote(name)}/128.svg[/img]\n"
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

        with self.ts_connection_pool.item() as ts3conn:
            ts3_facade = TS3Facade(ts3conn)
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

            return SUCCESS
