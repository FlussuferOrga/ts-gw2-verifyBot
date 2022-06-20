import logging
import urllib.parse
from enum import Enum
from typing import Dict, Optional

from .config import Config
from .connection_pool import ConnectionPool
from .ts import TS3Facade, User
from .user_service import UserService
from .util import strip_ts_channel_name_tags

LOG = logging.getLogger(__name__)


class LeadType(str, Enum):
    UNKNOWN = 'UNKNOWN'
    PPT = 'PPT'
    PPK = 'PPK'


class CommanderService:
    def __init__(self, ts_connection_pool: ConnectionPool[TS3Facade], user_service: UserService, config: Config):
        self._commander_group_names = config.poll_group_names
        self._ts_connection_pool = ts_connection_pool
        self._user_service = user_service

        self._server_public_address = config.server_public_address
        self._server_public_port = config.server_public_port
        self._server_public_password = config.server_public_password

        with self._ts_connection_pool.item() as facade:
            channel_list, ex = facade.channelgroup_list()
            cgroups = list(filter(lambda g: g.get("name") in self._commander_group_names, channel_list))

            server_info = facade.server_info()
            self._vs_port = server_info.get("virtualserver_port")

            if len(server_info.get("virtualserver_password", "")) > 0 and self._server_public_password is None:
                LOG.warning("Server is password protected, but no password is configured in the config. "
                            "Links will not be usable without a password")

        if len(cgroups) < 1:
            LOG.info("Could not find any group of %s to determine commanders by. Disabling this feature.",
                     str(self._commander_group_names))
            self._commander_groups = []
            return

        self._commander_groups = [
            {
                "cgid": c.get("cgid"),
                "leadtype": CommanderService.extract_type(c.get("name"))
            } for c in cgroups
        ]

    @staticmethod
    def extract_type(group_name) -> LeadType:
        if "PPK" in group_name:
            return LeadType.PPK
        elif "PPT" in group_name:
            return LeadType.PPT
        else:
            return LeadType.UNKNOWN

    def get_active_commanders(self):
        if not self._commander_groups:
            return  # disabled if no groups were found

        active_commanders = []

        with self._ts_connection_pool.item() as ts_facade:
            acs = ts_facade.channelgroup_client_list([g["cgid"] for g in self._commander_groups])
            LOG.info(acs)
            for ts_entry in acs:
                client_dbid = ts_entry.get("cldbid")
                user = User(ts_facade, ts_db_id=client_dbid)
                channel = user.current_channel
                lead_channel_id = ts_entry.get("cid")
                if channel is not None and channel.id == lead_channel_id:  # user not online or in channel
                    # user could have the group in a channel but not be in there atm
                    ac = {
                        "ts_cluid": user.unique_id,
                        "ts_display_name": user.name
                    }

                    for e in self._commander_groups:
                        if e["cgid"] == ts_entry.get("cgid"):
                            ac["leadtype"] = e["leadtype"]
                            break

                    db_entry = self._user_service.get_user_database_entry(user.unique_id)

                    if db_entry is not None:
                        ac["account_name"] = db_entry["account_name"]

                    ex, path = self.fetch_branch(lead_channel_id, ts_facade)

                    display_path = list(map(strip_ts_channel_name_tags, path))
                    ac["ts_channel_name"] = display_path[0]  # channel the commander is in
                    ac["ts_channel_path"] = display_path[::-1]  # tree branch (reverse)

                    ac["ts_join_url"] = self._create_join_link(lead_channel_id)  # tree branch (reverse)

                    if ex is not None:
                        LOG.warning("Could not determine information for commanding user with ID %s: '%s'. Skipping.",
                                    str(ts_entry), str(ex))
                    else:
                        active_commanders.append(ac)

            return {"commanders": active_commanders}

    @staticmethod
    def fetch_branch(lead_cid, ts_facade):
        ex = None
        path = []
        cid = lead_cid
        while cid is not None:
            channel_info, ex = ts_facade.channel_info(channel_id=cid)
            path.append(channel_info.get("channel_name"))
            if channel_info.get("pid") is None or channel_info.get('pid') == '0':
                cid = None
            else:
                cid = channel_info.get("pid")
        return ex, path

    def _create_join_link(self, channel_id: Optional[str]) -> str:
        args: Dict[str] = {}

        if self._server_public_password is not None and self._server_public_password != "":
            args["password"] = self._server_public_password

        if self._server_public_port:
            if self._server_public_port == "auto":
                if self._vs_port != "9987":
                    args["port"] = self._vs_port
            else:
                args["port"] = self._server_public_port

        if channel_id is not None:
            args["cid"] = channel_id

        servername = self._server_public_address
        return self._build_url("https://invite.teamspeak.com", "%s/" % servername, args)

    @staticmethod
    def _build_url(base_url, path, args_dict):
        # Returns a list in the structure of urlparse.ParseResult
        url_parts = list(urllib.parse.urlparse(base_url))
        url_parts[2] = path
        url_parts[4] = urllib.parse.urlencode(args_dict)
        return urllib.parse.urlunparse(url_parts)
