import ast  # eval a string to a list/boolean (for cmd_list from 'bot settings' or DEBUG from config)
import configparser  # parse in configuration
import logging

from bot.messages import Locale, get_locale

LOG = logging.getLogger(__name__)


class Config:
    def __init__(self, config_file_path: str) -> None:
        self.current_version = "1.5"

        configs = configparser.ConfigParser()
        configs.read(config_file_path, "utf-8")

        # Features
        self.enable_verification = self._try_get(configs, "features", "enable_verification", True, True)
        self.enable_guild_audit = self._try_get(configs, "features", "enable_guild_audit", True, True)

        # Teamspeak Connection Settings
        self.protocol = configs.get("teamspeak connection settings", "protocol", fallback="telnet")  # telnet or ssh
        self.host = configs.get("teamspeak connection settings", "host")
        self.port = configs.get("teamspeak connection settings", "port")
        self.user = configs.get("teamspeak connection settings", "user")
        self.passwd = configs.get("teamspeak connection settings", "passwd")
        self.known_hosts_file = configs.get("teamspeak connection settings", "known_hosts_file", fallback=None)

        self.pool_size = self._try_get(configs, "teamspeak connection settings", "pool_size", 4)
        self.pool_ttl = self._try_get(configs, "teamspeak connection settings", "pool_ttl", 600)
        self.pool_tti = self._try_get(configs, "teamspeak connection settings", "pool_tti", 120)
        self.pool_max_usage = self._try_get(configs, "teamspeak connection settings", "pool_max_usage", 25)

        # Teamspeak Other Settings
        self.server_id = configs.get("teamspeak other settings", "server_id")
        self.server_public_address = configs.get("teamspeak other settings", "server_public_address",
                                                 fallback=self.host)
        self.server_public_password = configs.get("teamspeak other settings", "server_public_password", fallback=None)
        self.server_public_port = configs.get("teamspeak other settings", "server_public_port", fallback="auto")
        self.channel_name = configs.get("teamspeak other settings", "channel_name")
        self.verified_group = configs.get("teamspeak other settings", "verified_group")
        self.verified_group_id = -1  # will be cached later

        # BOT Settings
        # this setting is technically not required anymore. It just shouldn"t exceed 5 minutes to avoid timeouts.
        # An appropriate user warning will be given.
        self.bot_nickname = configs.get("bot settings", "bot_nickname")
        self.bot_sleep_conn_lost = int(configs.get("bot settings", "bot_sleep_conn_lost"))
        self.bot_sleep_idle = int(configs.get("bot settings", "bot_sleep_idle"))
        self.cmd_list = ast.literal_eval(configs.get("bot settings", "cmd_list"))
        self.db_file_name = configs.get("bot settings", "db_file_name")
        self.audit_period = int(
            configs.get("bot settings", "audit_period"))  # How long a single user can go without being audited
        self.audit_interval = int(configs.get("bot settings", "audit_interval"))  # how often the BOT audits all users
        self.client_restriction_limit = int(configs.get("bot settings", "client_restriction_limit"))

        # tryGet(config, section, key, default = None, lit_eval = False):
        self.purge_completely = self._try_get(configs, "bot settings", "purge_completely", False, True)
        self.purge_whitelist = self._try_get(configs, "bot settings", "purge_whitelist", ["Server Admin"], True)

        # Auth settings
        self.required_servers = ast.literal_eval(configs.get("auth settings",
                                                             "required_servers"))  # expects a pythonic list, Ex. ["Tarnished Coast","Kaineng"]
        self.required_level = configs.get("auth settings", "required_level")

        # IPC settings
        self.ipc_port = int(configs.get("ipc settings", "ipc_port"))

        self.poll_group_names = ast.literal_eval(configs.get("ipc settings", "poll_group_names"))

        # Reset Roster
        reset_top_level_channel = ast.literal_eval(configs.get("reset roster", "reset_top_level_channel"))
        reset_rgl_channel = ast.literal_eval(configs.get("reset roster", "reset_rgl_channel"))
        reset_ggl_channel = ast.literal_eval(configs.get("reset roster", "reset_ggl_channel"))
        reset_bgl_channel = ast.literal_eval(configs.get("reset roster", "reset_bgl_channel"))
        reset_ebg_channel = ast.literal_eval(configs.get("reset roster", "reset_ebg_channel"))
        self.reset_channels = (reset_top_level_channel, reset_rgl_channel, reset_ggl_channel, reset_bgl_channel,
                               reset_ebg_channel)  # convenience list

        # Create Guild
        self.guilds_parent_channel = configs.get("guilds", "guilds_parent_channel")
        self.guild_sub_channels = ast.literal_eval(configs.get("guilds", "guild_sub_channels"))
        self.guilds_minimum_talk_power = int(configs.get("guilds", "minimum_talk_power"))
        self.guilds_maximum_talk_power = int(configs.get("guilds", "maximum_talk_power"))
        self.guilds_sort_id = int(configs.get("guilds", "guild_sort_id"))
        self.guild_contact_channel_group = configs.get("guilds", "guild_contact_channel_group")

        # Constants
        self.keepalive_interval = 60
        self.debug = ast.literal_eval(configs.get("DEBUGGING", "DEBUG"))  # Debugging (on or off) True/False

        # Locale
        locale_setting = self._try_get(configs, "bot settings", "locale", "EN")
        self.locale: Locale = get_locale(locale_setting)

        if self.bot_sleep_idle > 300:
            LOG.warning("Setting bot_sleep_idle to a value higher than 300 seconds could result in timeouts!")

    @staticmethod
    def _try_get(config, section, key, default=None, lit_eval=False):
        try:
            val = config.get(section, key)
            if lit_eval:
                val = ast.literal_eval(val)
        except configparser.NoOptionError:
            LOG.warning("No config setting '%s' found in the section [%s]. Falling back to '%s'.", key, section,
                        str(default))
            val = default
        return val
