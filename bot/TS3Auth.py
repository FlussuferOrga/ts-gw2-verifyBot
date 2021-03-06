import logging

import bot.gwapi as gw2api

LOG = logging.getLogger(__name__)

# String handles
h_hdr = '#~ GW2 Handler:'  # Header
h_acct = '[AccountGet]'  # Account loading
h_char = '[CharacterGet]'  # Character loading
h_auth = '[AuthCheck]'
h_char_chk = '[CharacterCheck]'


#############################

class AuthorizationNotPossibleError(RuntimeError):
    pass


# Class for an authentication request from user

class AuthRequest:
    def __init__(self, api_key, required_servers, required_level,
                 user_id=''):  # User ID left at None for queries that don't require authentication. If left at None the 'success' will always fail due to self.authCheck().
        self.key = api_key
        self.user = user_id
        self.success = False  # Used to verify if user is on our server
        self.char_check = False  # Used to verify is any character is at least 80
        self.required_level = required_level
        self.required_servers = required_servers
        self.account_details = {}
        self.world = None
        self.users_server = None
        self.name = None
        self.id = -1
        self.guilds_error = False
        self.guilds = []

        self.guild_tags = []
        self.guild_names = []

        self.pushCharacterAuth()
        self.pushAccountAuth()

    def pushCharacterAuth(self):
        if self.required_level == 0:  # if level is set to 0 bypass character API request (in case GW2 Character API breaks again like in April 2016.)
            self.char_check = True
            return
        try:
            LOG.info("%s %s Attempting to load character data for %s.", h_hdr, h_char, self.user)
            self.char_dump = gw2api.characters_get(self.key)
            LOG.info("%s %s Character data loaded for %s.", h_hdr, h_char, self.user)
            self.charCheck()
        except gw2api.ApiUnavailableError as ex:
            raise AuthorizationNotPossibleError from ex
        except gw2api.ApiError:
            LOG.error("%s %s Unable to load character data for %s. Bad API key or API key is not set to allow 'character' queries.", h_hdr, h_char, self.user)

    def pushAccountAuth(self):
        try:
            self.getAccountDetails()
            LOG.info("%s %s Account loaded for %s", h_hdr, h_acct, self.user)
            self.authCheck()
        except gw2api.ApiUnavailableError as ex:
            raise AuthorizationNotPossibleError from ex
        except gw2api.ApiError:
            LOG.error("%s %s Possibly bad API Key. Error obtaining account details for %s. (Does the API key allow 'account' queries?)", h_hdr, h_acct, self.user)

    def getAccountDetails(self):
        # All account details
        self.account_details = gw2api.account_get(self.key)

        # Players World [id,name,population]
        self.world = gw2api.worlds_get_one(self.account_details.get('world'))
        self.users_server = self.world.get('name')

        # Player Created Date -- May be useful to flag accounts created within past 30 days
        # self.created = self.details_dump.get('created')

        # Player Name
        self.name = self.account_details.get('name')

        # Players Account ID
        self.id = self.account_details.get('id')

        # Players Guilds (by ID)
        self.guilds = self.account_details.get('guilds')
        self.guilds_error = False

        # Players Guild Tags (Seems to order it by oldest guild first)

        for guild_id in self.guilds:
            try:
                ginfo = gw2api.guild_get(guild_id)
                self.guild_tags.append(ginfo.get('tag'))
                self.guild_names.append(ginfo.get('name'))
            except gw2api.ApiError as ex:
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
