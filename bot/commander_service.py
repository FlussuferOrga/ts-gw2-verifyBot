import logging

from bot.config import Config
from bot.ts.user import User
from .connection_pool import ConnectionPool
from .ts import TS3Facade
from .user_service import UserService

LOG = logging.getLogger(__name__)


class CommanderService:
    def __init__(self, ts_connection_pool: ConnectionPool[TS3Facade], user_service: UserService, config: Config):
        self._commander_group_names = config.poll_group_names
        self._ts_connection_pool = ts_connection_pool
        self._user_service = user_service

        with self._ts_connection_pool.item() as facade:
            channel_list, ex = facade.channelgroup_list()
            cgroups = list(filter(lambda g: g.get("name") in self._commander_group_names, channel_list))
        if len(cgroups) < 1:
            LOG.info("Could not find any group of %s to determine commanders by. Disabling this feature.", str(self._commander_group_names))
            self._commander_groups = []
            return

        self._commander_groups = [c.get("cgid") for c in cgroups]

    def get_active_commanders(self):
        if not self._commander_groups:
            return  # disabled if no groups were found

        active_commanders = []

        with self._ts_connection_pool.item() as ts_facade:
            acs = ts_facade.channelgroup_client_list(self._commander_groups)
            LOG.info(acs)
            for ts_entry in acs:
                client_dbid = ts_entry.get("cldbid")
                user = User(ts_facade, ts_db_id=client_dbid)
                channel = user.current_channel
                if channel is not None and channel.channel_id == ts_entry.get("cid"):  # user not online or in channel
                    db_entry = self._user_service.get_user_database_entry(user.unique_id)
                    # user could have the group in a channel but not be in there atm
                    ac = {
                        "account_name": db_entry["account_name"],
                        "ts_cluid": user.unique_id,
                        "ts_display_name": user.name
                    }

                    path = []
                    cid = ts_entry.get("cid")
                    while cid is not None:
                        channel_info, ex = ts_facade.channel_info(channel_id=cid)
                        LOG.error(ex)
                        path.append(channel_info.get("channel_name"))
                        if channel_info.get("pid") is None or channel_info.get('pid') == '0':
                            cid = None
                        else:
                            cid = channel_info.get("pid")

                    ac["ts_channel_name"] = path[0]  # channel the commander is in
                    ac["ts_channel_path"] = path[::-1]  # tree branch (reverse)

                    if ex is not None:
                        LOG.warning("Could not determine information for commanding user with ID %s: '%s'. Skipping.", str(ts_entry), str(ex))
                    else:
                        active_commanders.append(ac)
            return {"commanders": active_commanders}
