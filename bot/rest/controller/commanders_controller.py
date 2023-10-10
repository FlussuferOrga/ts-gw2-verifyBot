import logging

import timeout_decorator
from werkzeug.exceptions import abort

from bot.commander_service import CommanderService
from bot.rest.controller.abstract_controller import AbstractController

LOG = logging.getLogger(__name__)


class CommandersController(AbstractController):
    def __init__(self, commander_service: CommanderService):
        super().__init__()
        self._commander_service = commander_service

    def _routes(self):

        @timeout_decorator.timeout(seconds=30)
        @self.api.route("/commanders", methods=["GET"])
        def _active_commanders():
            acs = self._commander_service.get_active_commanders()
            return acs if acs is not None else abort(503)
