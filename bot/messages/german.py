from bot.messages.english import English
from bot.messages.locale import Locale


class German(Locale):
    def __init__(self):
        super().__init__(fallback=English())
        self.set("bot_msg_example", "\n\nBeispiel:\n\t\t7895D172-4991-9546-CB5B-78B015B0D8A72BC0E007-4FAF-48C3-9BF1-DA1OAD241266")
        self.set("bot_msg_note", "\n\nINFO: Guild Wars 2 API keys können über die ArenaNet-Seite [URL]account.arena.net/applications[/URL] erstellt/gelöscht werden.")
        self.set("bot_msg_verify",
                 "Hallöchen! Möchtest du dich registrieren?\n\n"
                 "Falls ja, antworte bitte per PRIVATER NACHRICHT mit deinem API-Key. "
                 "Bitte achte darauf, dass der Key die Berechtigungen [b]account[/b] und [b]characters[/b] besitzt."
                 + self.get("bot_msg_example") + self.get("bot_msg_note"))

        # Banner that we send to all users upon initialization
        self.set("bot_msg", "%s ist wieder da! Falls du eine Freischaltung benötigst, verbinde dich bitte neu!")

        # Broadcast message
        self.set("bot_msg_broadcast", "Hallöchen! Du kannst die Freischaltung beginnen, indem du 'verifyme' in diesem Channel schreibst.")

        # Message sent for sucesful verification
        self.set("bot_msg_success",
                 "Freischaltung erfolgreich! Danke dir, Abenteurer."
                 " Bitte lies dir unsere Regeln durch und dann viel Spaß \\(^.^)/ "
                 "Falls du keine User sehen kannst, relogge dich bitte einmal.")

        # Message sent for failed verification
        self.set("bot_msg_fail",
                 "Leider hat die Freischaltung nicht funktioniert."
                 " Bitte einen Teamspeak Administrator die Logs zu prüfen.\n"
                 "~ Wahrscheinlich ein ungültiger API-Schlüssel oder falsche API-Einstellungen."
                 " (Der API-Schlüssel braucht die Berechtigungen 'account' und 'character' )" + self.get("bot_msg_note"))

        # Message sent for client TS ID limit reached (trying to access Teamspeack from a second computer after having authenticated on a prior machine
        self.set("bot_msg_limit_Hit",
                 "Die Teamspeak Admins haben ein Limit gesetzt, auf wie vielen Geräten du dich mit deinem Guild Wars 2"
                 " Account freischalten kannst. Du bist bereits von einem anderen Gerät aus registriert "
                 "(oder du hat Teamspeak neu installiert, wodurch deine Teamspeak ID für diesen Server zurückgesetzt wurde).")

        # Message sent to someone who is already verified but asks to be verified
        self.set("bot_msg_alrdy_verified", "Es scheint, als seist du bereits freigeschaltet! Wieso quälst du mich sooo /cry")

        # Message sent to someone who is not verified but asks to set guild tags via channel text.
        self.set("bot_msg_sguild_nv",
                 "Tut mir leid, ich kann dir erst dabei helfen, ein Gildentag zu setzen, sobald du freigeschaltet bist. "
                 "Bitte schalte dich frei, indem du mir mit einem API-Schlüssel antwortest."
                 + self.get("bot_msg_example") + self.get("bot_msg_note"))

        # Message sent to someone who is verified and asks to set guild tags.
        self.set("bot_msg_sguild", "Lass uns anfangen! Zuerst brauche ich deinen API-Schlüssel. Antworte mir mit deinem API-Schlüssel:" + self.get("bot_msg_example") + self.get("bot_msg_note"))

        # Message sent to someone who is not verified and asks to set guild tags via private message.
        self.set("bot_msg_gld_needs_auth",
                 "Wolltest du dein Gildentag ändern? Falls ja, beachte, dass du noch nicht freigeschaltet bist! Lies weiter, um dich freizuschalten." + self.get("bot_msg_example"))

        # Base Message sent to someone who gave us the API key to pull guild tags.
        self.set("bot_msg_gld_lis", "API-Freischaltung erfolgreich. Sitzung erstellt. Hier sind die Gildentags, aus denen du wählen kannst:")

        # Default message we send to Private messages that didn't match a command
        self.set("bot_msg_rcv_default",
                 "Hm... ich merke, dass du etwas von mir willst, aber ich verstehe dich nicht. "
                 "Möchtest du dich freischalten? Falls ja, bitte gib deinen API-Schlüssel in folgendem Format an:"
                 + self.get("bot_msg_example") + self.get("bot_msg_note"))

        # User successfully hid a guild
        self.set("bot_hide_guild_success", "Okay, ich werde dir diese Gruppe bei der Revalidierung nichtmehr geben. Du kannst die Gruppe jederzeit wieder [b]unhideguild[/b]n.")

        # User passed an invalid guild
        self.set("bot_hide_guild_unknown",
                 "Tut mir Leid, eine solche Gilde scheint es nicht zu geben oder du hast sie bereits versteckt. "
                 "Bitte stelle sicher, dass du die exakte Schreibweise der Gildengruppe hier im Teamspeak verwendest.")

        # User passed an invalid hide guild command
        self.set("bot_hide_guild_help", "Bitte nutze folgendes Format: hideguild TAG")

        # User passed an invalid unhide guild command
        self.set("bot_unhide_guild_help", "Bitte nutze folgendes Format: unhideguild TAG")

        # User successfully hid a guild
        self.set("bot_unhide_guild_success", "Okay, du wirst die Gruppe bei der nächsten Revalidierung wieder erhalten, wenn du dazu berechtigt bist.")

        # User passed an invalid guild
        self.set("bot_unhide_guild_unknown",
                 "Tut mir Leid, eine solche Gilde scheint es nicht zu geben or du hattest die Gruppe nicht versteckt."
                 " Bitte stelle sicher, dass du die exakte Schreibweise der Gildengruppe hier im Teamspeak verwendest.")

        self.set("bot_pong_response", "Pong! Ich lebe noch!")
