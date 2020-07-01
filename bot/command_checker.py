import logging

from bot.ts import signal_exception_handler
from bot.ts.user import User

LOG = logging.getLogger(__name__)


class CommanderChecker:
    def __init__(self, ts3bot, commander_group_names):
        self.commander_group_names = commander_group_names
        self.ts3bot = ts3bot

        cgroups = list(filter(lambda g: g.get("name") in commander_group_names, self.ts3bot.ts_connection.ts3exec(lambda t: t.query("channelgrouplist").all())[0]))
        if len(cgroups) < 1:
            LOG.info("Could not find any group of %s to determine commanders by. Disabling this feature.", str(commander_group_names))
            self.commander_groups = []
            return

        self.commander_groups = [c.get("cgid") for c in cgroups]

    def execute(self):
        if not self.commander_groups:
            return  # disabled if no groups were found

        active_commanders = []

        def retrieve_commanders(tsc):
            command = tsc.query("channelgroupclientlist")
            for cgid in self.commander_groups:
                command.pipe(cgid=cgid)
            return command.all()

        acs, ts3qe = self.ts3bot.ts_connection.ts3exec(retrieve_commanders, signal_exception_handler)
        if ts3qe:  # check for .resp, could be another exception type
            if ts3qe.resp is not None:
                if ts3qe.resp.error["id"] != "1281":
                    # 1281 is "database empty result set", which is an expected error
                    # if not a single user currently wears a tag.
                    LOG.error("Error while trying to resolve active commanders: %s.", str(ts3qe))
            else:
                LOG.error(ts3qe)
        else:
            active_commanders_entries = [(c, self.ts3bot.getUserDBEntry(self.ts3bot.getTsUniqueID(c.get("cldbid")))) for c in acs]
            for ts_entry, db_entry in active_commanders_entries:
                if db_entry is not None:  # or else the user with the commander group was not registered and therefore not in the DB
                    user = User(self.ts3bot.ts_connection, ts_db_id=ts_entry.get("cldbid"))
                    if user.current_channel.channel_id == ts_entry.get("cid"):
                        # user could have the group in a channel but not be in there atm
                        ac = {"account_name": db_entry["account_name"], "ts_cluid": db_entry["ts_db_id"]}
                        ac["ts_display_name"], ex1 = self.ts3bot.ts_connection.ts3exec(
                            lambda t, cluid=db_entry["ts_db_id"]: t.query("clientgetnamefromuid", cluid).first().get("name"))  # no, there is probably no easier way to do this. I checked.
                        ac["ts_channel_name"], ex2 = self.ts3bot.ts_connection.ts3exec(lambda t, cid=ts_entry.get("cid"): t.query("channelinfo", cid=cid).first().get("channel_name"))
                        if ex1 or ex2:
                            LOG.warning("Could not determine information for commanding user with ID %s: '%s'. Skipping.", str(ts_entry), ", ".join([str(e) for e in [ex1, ex2] if e is not None]))
                        else:
                            active_commanders.append(ac)
        return {"commanders": active_commanders}
