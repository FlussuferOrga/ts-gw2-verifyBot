import logging

from bot.ts import TS3Facade
from bot.ts.user import User

LOG = logging.getLogger(__name__)


class CommanderChecker:
    def __init__(self, ts3bot, commander_group_names):
        self._commander_group_names = commander_group_names
        self._ts3bot = ts3bot

        with self._ts3bot.ts_connection_pool.item() as ts_connection:
            facade = TS3Facade(ts_connection)
            channel_list, ex = facade.channelgroup_list()
            cgroups = list(filter(lambda g: g.get("name") in commander_group_names, channel_list))
        if len(cgroups) < 1:
            LOG.info("Could not find any group of %s to determine commanders by. Disabling this feature.", str(commander_group_names))
            self._commander_groups = []
            return

        self._commander_groups = [c.get("cgid") for c in cgroups]

    def execute(self):
        if not self._commander_groups:
            return  # disabled if no groups were found

        active_commanders = []

        with self._ts3bot.ts_connection_pool.item() as ts_connection:
            ts_facade = TS3Facade(ts_connection)
            acs = ts_facade.channelgroup_client_list(self._commander_groups)
            LOG.info(acs)
            active_commanders_entries = [(c, self._ts3bot.getUserDBEntry(self._ts3bot.getTsUniqueID(c.get("cldbid")))) for c in acs]
            for ts_entry, db_entry in active_commanders_entries:
                if db_entry is not None:  # or else the user with the commander group was not registered and therefore not in the DB
                    user = User(ts_connection, ts_db_id=ts_entry.get("cldbid"))
                    if user.current_channel.channel_id == ts_entry.get("cid"):
                        # user could have the group in a channel but not be in there atm
                        ac = {"account_name": db_entry["account_name"], "ts_cluid": db_entry["ts_db_id"]}

                        name_resp, ex1 = ts_facade.client_get_name_from_uid(db_entry["ts_db_id"])
                        LOG.error(ex1)
                        ac["ts_display_name"] = name_resp.get("name")

                        path = []
                        cid = ts_entry.get("cid")
                        while cid is not None:
                            channel_info, ex2 = ts_facade.channel_info(channel_id=cid)
                            LOG.error(ex2)
                            path.append(channel_info.get("channel_name"))
                            if channel_info.get("pid") is None or channel_info.get('pid') == '0':
                                cid = None
                            else:
                                cid = channel_info.get("pid")

                        ac["ts_channel_name"] = path[0]  # channel the commander is in
                        ac["ts_channel_path"] = path[::-1]  # tree branch (reverse)

                        if ex1 or ex2:
                            LOG.warning("Could not determine information for commanding user with ID %s: '%s'. Skipping.", str(ts_entry), ", ".join([str(e) for e in [ex1, ex2] if e is not None]))
                        else:
                            active_commanders.append(ac)
            return {"commanders": active_commanders}
