import configparser # parse in configuration
import ast #eval a string to a list/boolean (for cmd_list from 'bot settings' or DEBUG from config)
import bot_messages

#######################################
#### Load Configs
#######################################

def tryGet(config, section, key, default = None, lit_eval = False):
    val = default
    try:
        val = config.get(section,key)
        if lit_eval: 
            val = ast.literal_eval(val)
    except configparser.NoOptionError:
        TS3Auth.log("No config setting '%s' found in the section [%s]. Falling back to '%s'." % (key, section, str(default)))
        val = default 
    return val

current_version="1.5"

configs = configparser.ConfigParser()
configs.read("bot.conf")

# Teamspeak Connection Settings
host = configs.get("teamspeak connection settings","host")
port = configs.get("teamspeak connection settings","port")
user = configs.get("teamspeak connection settings","user")
passwd = configs.get("teamspeak connection settings","passwd")

# Teamspeak Other Settings
server_id = configs.get("teamspeak other settings","server_id")
channel_name = configs.get("teamspeak other settings","channel_name")
verified_group = configs.get("teamspeak other settings","verified_group")
verified_group_id = -1 # will be cached later

# BOT Settings
# this setting is technically not required anymore. It just shouldn"t exceed 5 minutes to avoid timeouts. 
# An appropriate user warning will be given.
bot_nickname = configs.get("bot settings","bot_nickname")
bot_sleep_conn_lost = int(configs.get("bot settings","bot_sleep_conn_lost"))
bot_sleep_idle = int(configs.get("bot settings","bot_sleep_idle"))
cmd_list = ast.literal_eval(configs.get("bot settings","cmd_list"))
db_file_name = configs.get("bot settings","db_file_name")
audit_period = int(configs.get("bot settings","audit_period")) #How long a single user can go without being audited
audit_interval = int(configs.get("bot settings","audit_interval")) # how often the BOT audits all users
client_restriction_limit= int(configs.get("bot settings","client_restriction_limit"))
timer_msg_broadcast = int(configs.get("bot settings","broadcast_message_timer"))

# tryGet(config, section, key, default = None, lit_eval = False):
locale_setting = tryGet(configs, "bot settings", "locale", "EN")
purge_completely = tryGet(configs, "bot settings", "purge_completely", False, True)
purge_whitelist = tryGet(configs, "bot settings", "purge_whitelist", ["Server Admin"], True)

# Auth settings
required_servers = ast.literal_eval(configs.get("auth settings","required_servers")) # expects a pythonic list, Ex. ["Tarnished Coast","Kaineng"]
required_level = configs.get("auth settings","required_level")

# IPC settings
ipc_port = int(configs.get("ipc settings","ipc_port"))

poll_group_names = ast.literal_eval(configs.get("ipc settings","poll_group_names"))
poll_group_poll_delay = int(configs.get("ipc settings","poll_group_poll_delay"))

# Reset Roster
reset_top_level_channel = ast.literal_eval(configs.get("reset roster", "reset_top_level_channel"))
reset_rgl_channel = ast.literal_eval(configs.get("reset roster", "reset_rgl_channel"))
reset_ggl_channel = ast.literal_eval(configs.get("reset roster", "reset_ggl_channel"))
reset_bgl_channel = ast.literal_eval(configs.get("reset roster", "reset_bgl_channel"))
reset_ebg_channel = ast.literal_eval(configs.get("reset roster", "reset_ebg_channel"))
reset_channels = (reset_top_level_channel, reset_rgl_channel, reset_ggl_channel, reset_bgl_channel, reset_ebg_channel) # convenience list

# Constants
keepalive_interval = 60
DEBUG = ast.literal_eval(configs.get("DEBUGGING","DEBUG")) # Debugging (on or off) True/False

# Convenience 
locale = bot_messages.getLocale(locale_setting)
if bot_sleep_idle > 300:
    TS3Auth.log("WARNING: setting bot_sleep_idle to a value higher than 300 seconds could result in timeouts!")