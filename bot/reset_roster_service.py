import logging
from datetime import datetime
from typing import Optional

import pytz

from bot import ts
from bot.config import Config
from bot.connection_pool import ConnectionPool
from bot.util import StringShortener

LOG = logging.getLogger(__name__)

TS3_MAX_SIZE_CHANNEL_NAME = 40
DISPLAY_TIMEZONE = pytz.timezone("Europe/Berlin")
RESET_TIME_FORMAT = "%d.%m.%Y %H:%M %Z"


class ResetRosterService:
    def __init__(self, ts_connection_pool: ConnectionPool[ts.TS3Facade], config: Config):
        self._config = config
        self._ts_connection_pool = ts_connection_pool

    def set_reset_roster(self, date: Optional[datetime], red=None, green=None, blue=None, ebg=None):
        leads = (
            [],
            red if red is not None else [],
            green if green is not None else [],
            blue if blue is not None else [],
            ebg if ebg is not None else []
        )  # keep RGB order! EBG as last! Pad first slot (header) with empty list

        if date is not None:
            date_as_str = date.astimezone(DISPLAY_TIMEZONE).strftime(RESET_TIME_FORMAT)
        else:
            date_as_str = ""

        with self._ts_connection_pool.item() as facade:
            channels = [(p, c.replace("$DATE", date_as_str)) for p, c in self._config.reset_channels]
            for i, reset_channel in enumerate(channels):
                pattern, clean = reset_channel
                lead = leads[i]

                shortened = StringShortener(TS3_MAX_SIZE_CHANNEL_NAME - len(clean)).shorten(lead)
                new_channel_name = "%s%s" % (clean, ", ".join(shortened))

                self._rename_channel_if_exists(facade, pattern, new_channel_name)
        return 0

    @staticmethod
    def _rename_channel_if_exists(facade, channel_name_pattern, new_channel_name):
        channel = facade.channel_find_first(channel_name_pattern)
        if channel is None:
            LOG.warning("No channel found with pattern '%s'. Skipping.", channel_name_pattern)
        else:
            _, ts3qe = facade.channel_edit(channel_id=channel.channel_id, new_channel_name=new_channel_name)
            if ts3qe is not None and ts3qe.resp.error["id"] == "771":
                # channel name already in use
                # probably not a bug (channel still unused), but can be a config problem
                LOG.info("Channel '%s' already exists. This is probably not a problem. Skipping.", new_channel_name)
