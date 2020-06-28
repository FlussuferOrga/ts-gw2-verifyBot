import logging

from werkzeug.exceptions import abort

from bot import Bot
from bot.rest.controller.abstract_controller import AbstractController

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
