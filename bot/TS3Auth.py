import logging

import gw2api.v2

from bot.Config import Config

LOG = logging.getLogger(__name__)

# log_file = 'TS3Auth.log'

# String handles
h_hdr = '#~ GW2 Handler:'  # Header
h_acct = '[AccountGet]'  # Account loading
h_char = '[CharacterGet]'  # Character loading
h_auth = '[AuthCheck]'
h_char_chk = '[CharacterCheck]'

#############################
# Functions

"""
def log(msg,silent=False):
    if not silent:
        print (msg)
        sys.stdout.flush()
    with open(log_file,"a") as logger:
        new_log = "%s %s\n" %(str(datetime.now()),msg)
        logger.write(new_log)
"""


# Class for an authentication request from user

class AuthRequest:
    def __init__(self, api_key, user_id=''):  # User ID left at None for queries that don't require authentication. If left at None the 'success' will always fail due to self.authCheck().
        self.key = api_key
        self.user = user_id
        self.success = False  # Used to verify if user is on our server
        self.char_check = False  # Used to verify is any character is at least 80
        self.required_level = int(Config.required_level)
        self.required_servers = Config.required_servers

        self.pushCharacterAuth()
        self.pushAccountAuth()

    def pushCharacterAuth(self):
        if self.required_level == 0:  # if level is set to 0 bypass character API request (in case GW2 Character API breaks again like in April 2016.)
            self.char_check = True
            return
        try:
            LOG.info("%s %s Attempting to load character data for %s.", h_hdr, h_char, self.user)
            gw2api.v2.characters.set_token(self.key)
            self.char_dump = gw2api.v2.characters.page(page=0)
            LOG.info("%s %s Character data loaded for %s.", h_hdr, h_char, self.user)
            self.charCheck()
        except Exception:
            LOG.error("%s %s Unable to load character data for %s. Bad API key or API key is not set to allow 'character' queries.", h_hdr, h_char, self.user)

    def pushAccountAuth(self):
        try:
            self.getAccountDetails()
            LOG.info("%s %s Account loaded for %s", h_hdr, h_acct, self.user)
            self.authCheck()
        except Exception:
            LOG.error("%s %s Possibly bad API Key. Error obtaining account details for %s. (Does the API key allow 'account' queries?)", h_hdr, h_acct, self.user)

    def getAccountDetails(self):
        gw2api.v2.account.set_token(self.key)

        # All account details
        self.details_dump = gw2api.v2.account.get()

        # Players World [id,name,population]
        self.world = gw2api.v2.worlds.get_one(self.details_dump.get('world'))
        self.users_server = self.world.get('name')

        # Player Created Date -- May be useful to flag accounts created within past 30 days
        # self.created = self.details_dump.get('created')

        # Player Name
        self.name = self.details_dump.get('name')

        # Players Account ID
        self.id = self.details_dump.get('id')

        # Players Guilds (by ID)
        self.guilds = self.details_dump.get('guilds')
        self.guilds_error = False

        # Players Guild Tags (Seems to order it by oldest guild first)
        self.guild_tags = []
        self.guild_names = []
        for guild_id in self.guilds:
            try:
                ginfo = gw2api.guild_details(guild_id)
                self.guild_tags.append(ginfo.get('tag'))
                self.guild_names.append(ginfo.get('guild_name'))
            except Exception as ex:
                LOG.error("Exception while trying to obtain details for guild '%s': %s", guild_id, str(ex))
                self.guilds_error = True

    def authCheck(self):
        LOG.info("%s %s Running auth check for %s", h_hdr, h_auth, self.name)

        # Check if they are on the required server
        if self.users_server in self.required_servers:
            # Check if player has met character requirements
            if self.char_check:
                self.success = True
                LOG.info("%s %s Auth Success for user %s.", h_hdr, h_auth, self.user)
            else:
                LOG.info("%s %s User %s is on the correct server %s but does not have any level %s characters.", h_hdr, h_auth, self.user, self.users_server, self.required_level)
        else:
            LOG.info("%s %s Authentication Failed with:\n\n    User Gave:\n        ~USER ID: %s\n          ~Server: %s\n\n     Expected:\n         ~USER ID: %s\n          ~Server: %s\n\n", h_hdr,
                     h_auth, self.user, self.users_server, self.name, self.required_servers)
        return self.success

    def charCheck(self):
        # Require at least 1 level 80 character (helps prevent spies)
        for char in self.char_dump:
            if char.get('level') >= self.required_level:
                self.char_check = True
                LOG.info("%s %s User %s has at least 1 level %s character.", h_hdr, h_char_chk, self.user, self.required_level)
                return
