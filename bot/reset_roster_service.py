import logging

from bot.config import Config
from .connection_pool import ConnectionPool
from .ts import TS3Facade
from .util import StringShortener

LOG = logging.getLogger(__name__)

TS3_MAX_SIZE_CHANNEL_NAME = 40


class ResetRosterService:
    def __init__(self, ts_connection_pool: ConnectionPool[TS3Facade], config: Config):
        self._config = config
        self._ts_connection_pool = ts_connection_pool

    def set_reset_roster(self, date, red=[], green=[], blue=[], ebg=[]):
        leads = ([], red, green, blue, ebg)  # keep RGB order! EBG as last! Pad first slot (header) with empty list

        with self._ts_connection_pool.item() as facade:
            channels = [(p, c.replace("$DATE", date)) for p, c in self._config.reset_channels]
            for i in range(len(channels)):
                pattern, clean = channels[i]
                lead = leads[i]

                shortened = StringShortener(TS3_MAX_SIZE_CHANNEL_NAME - len(clean)).shorten(lead)
                newname = "%s%s" % (clean, ", ".join(shortened))

                channel = facade.channel_find(pattern)
                if channel is None:
                    LOG.warning("No channel found with pattern '%s'. Skipping.", pattern)
                    return

                _, ts3qe = facade.channel_edit(channel_id=channel.channel_id, new_channel_name=newname)
                if ts3qe is not None and ts3qe.resp.error["id"] == "771":
                    # channel name already in use
                    # probably not a bug (channel still unused), but can be a config problem
                    LOG.info("Channel '%s' already exists. This is probably not a problem. Skipping.", newname)
        return 0
