from bot.messages.locale import Locale


class English(Locale):
    def __init__(self):
        super(English, self).__init__()
        self.set("bot_msg_example", "\n\nExample:\n\t\t7895D172-4991-9546-CB5B-78B015B0D8A72BC0E007-4FAF-48C3-9BF1-DA1OAD241266")
        self.set("bot_msg_note", "\n\nNOTE: Guild Wars 2 API keys can be created/deleted via ArenaNet site [URL]account.arena.net/applications[/URL].")
        self.set("bot_msg_verify", "Hello there! I believe you requested verification?\n\n"
                                   "If so please reply back to THIS PRIVATE MESSAGE with your API key. "
                                   "Please make sure the key has the permissions [b]account[/b] and [b]characters[/b]."
                 + self.get("bot_msg_example") + self.get("bot_msg_note"))

        # Banner that we send to all users upon initialization
        self.set("bot_msg", "%s is alive once again! If you require verification, please reconnect!")

        # Broadcast message
        self.set("bot_msg_broadcast", "Hello there! You can begin verification by typing 'verifyme' in this channel.")

        # Message sent for sucesful verification
        self.set("bot_msg_success", "Authentication was succesful! Thank you fellow adventurer. Please give our rules a read and have fun \\(^.^)/ If you don't see any people, please relog once.")

        # Message sent for failed verification
        self.set("bot_msg_fail",
                 "Unfortuntely your authentication failed. Ask the Teamspeak admin to review the logs.\n"
                 "~ Likely a bad API key or incorrect API settings. (API Key needs access to 'account' and 'character' )"
                 + self.get("bot_msg_note"))

        # Message sent for client TS ID limit reached (trying to access Teamspeack from a second computer after having authenticated on a prior machine
        self.set("bot_msg_limit_Hit",
                 "The TeamSpeak Admins have set a limit to how many computers can authenticate with your Guild Wars 2 account. "
                 "You are already authenticated from a different computer (or you reinstalled Teamspeak client which reset your TeamSpeak ID with this server).")

        # Message sent to someone who is already verified but asks to be verified
        self.set("bot_msg_alrdy_verified", "It looks like you are already verified! Why do you torture me sooo /cry")

        # Message sent to someone who is not verified but asks to set guild tags via channel text.
        self.set("bot_msg_sguild_nv",
                 "I'm sorry, I can't help you set guild tags unless you are authenticated. Please verify first by replying to me with your API key." + self.get("bot_msg_example") + self.get(
                     "bot_msg_note"))

        # Message sent to someone who is verified and asks to set guild tags.
        self.set("bot_msg_sguild", "Let's get to work! First, I need your API key. Reply back with your API key:" + self.get("bot_msg_example") + self.get("bot_msg_note"))

        # Message sent to someone who is not verified and asks to set guild tags via private message.
        self.set("bot_msg_gld_needs_auth", "Where you trying to change your guild tags? If so, please be aware you have not been verified yet! Read below to verify." + self.get("bot_msg_example"))

        # Base Message sent to someone who gave us the API key to pull guild tags.
        self.set("bot_msg_gld_lis", "API Authentication succeeded. Session built. Here are your guild TAGS your can choose to assign:")

        # Default message we send to Private messages that didn't match a command
        self.set("bot_msg_rcv_default",
                 "Hrm...So I get that your saying something but I don't understand what. Are you trying to get verified? If so please provide your API key in the format:" + self.get(
                     "bot_msg_example") + self.get("bot_msg_note"))

        # User successfully hid a guild
        self.set("bot_hide_guild_success", "Okay, I will not give you this tag again upon revalidation. You can [b]unhide[/b] the tag at any time.")

        # User passed an invalid guild
        self.set("bot_hide_guild_unknown", "Sorry, there seems to be no such guild or you have already hidden it. Please make sure you use the exact spelling that is used for the TS group.")

        # User successfully hid a guild
        self.set("bot_unhide_guild_success", "Okay, you will receive this group with the next revalidation, if you are entitled to get it.")

        # User passed an invalid guild
        self.set("bot_unhide_guild_unknown", "Sorry, there seems to be no such guild-group or you have not hidden it. Please make sure you use the exact spelling that is used for the TS group.")
