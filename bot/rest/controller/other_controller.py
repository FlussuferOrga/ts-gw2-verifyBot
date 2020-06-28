import logging

from flask import request
from werkzeug.exceptions import abort

from bot import Bot
from bot.rest import AbstractController
from bot.rest.utils import try_get

LOG = logging.getLogger(__name__)


class OtherController(AbstractController):
    def __init__(self, bot: Bot):
        super().__init__()
        self._bot = bot

    def _routes(self):
        @self.api.route("/resetroster", methods=["POST"])
        def _resetRoster():
            body = request.json
            date = try_get(body, "date", default="dd.mm.yyyy")
            red = try_get(body, "rbl", default=[])
            green = try_get(body, "gbl", default=[])
            blue = try_get(body, "bbl", default=[])
            ebg = try_get(body, "ebg", default=[])
            LOG.info("Received request to set resetroster. RBL: %s GBL: %s, BBL: %s, EBG: %s", ", ".join(red), ", ".join(green), ", ".join(blue), ", ".join(ebg))
            res = self._bot.setResetroster(date, red, green, blue, ebg)
            return "OK" if res == 0 else abort(400, res)

        @self.api.route("/registration", methods=["DELETE"])
        def _deleteRegistration():
            body = request.json
            gw2account = try_get(body, "gw2account", default="")
            LOG.info("Received request to delete user '%s' from the TS registration database.", gw2account)
            changes = self._bot.removePermissionsByGW2Account(gw2account)
            return {"changes": changes}

        @self.api.route("/commanders", methods=["GET"])
        def _activeCommanders():
            acs = self._bot.getActiveCommanders()
            return acs if acs is not None else abort(503, "")
