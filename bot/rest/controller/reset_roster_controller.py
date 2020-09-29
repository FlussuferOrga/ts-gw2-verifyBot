import logging

from flask import request
from werkzeug.exceptions import abort

from bot import Bot
from bot.rest.controller.abstract_controller import AbstractController
from bot.rest.utils import try_get

LOG = logging.getLogger(__name__)


class ResetRosterController(AbstractController):
    def __init__(self, bot: Bot):
        super().__init__()
        self._bot = bot

    def _routes(self):
        @self.api.route("/resetroster", methods=["POST"])
        def _reset_roster():
            body = request.json
            date = try_get(body, "date", default="dd.mm.yyyy")
            red = try_get(body, "rbl", default=[])
            green = try_get(body, "gbl", default=[])
            blue = try_get(body, "bbl", default=[])
            ebg = try_get(body, "ebg", default=[])
            LOG.info("Received request to set resetroster. RBL: %s GBL: %s, BBL: %s, EBG: %s", ", ".join(red), ", ".join(green), ", ".join(blue), ", ".join(ebg))
            res = self._bot.set_reset_roster(date, red, green, blue, ebg)
            return "OK" if res == 0 else abort(400, res)
