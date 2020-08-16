import logging

from flask import request
from werkzeug.exceptions import abort

from bot import Bot
from bot.rest.controller.abstract_controller import AbstractController
from bot.rest.utils import try_get

LOG = logging.getLogger(__name__)


class OtherController(AbstractController):
    def __init__(self, bot: Bot):
        super().__init__()
        self._bot = bot

    def _routes(self):
        @self.api.route("/commanders", methods=["GET"])
        def _active_commanders():
            acs = self._bot.getActiveCommanders()
            return acs if acs is not None else abort(503, "")

        @self.api.route("/registration", methods=["DELETE"])
        def _delete_registration():
            body = request.json
            gw2account = try_get(body, "gw2account", default="")
            LOG.info("Received request to delete user '%s' from the TS registration database.", gw2account)
            changes = self._bot.removePermissionsByGW2Account(gw2account)
            return {"changes": changes}
