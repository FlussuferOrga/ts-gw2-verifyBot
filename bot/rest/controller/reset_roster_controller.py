import logging
from datetime import datetime
from typing import Optional

from flask import request
from timeout_decorator import timeout_decorator
from werkzeug.exceptions import abort

from bot import ResetRosterService
from bot.rest.controller.abstract_controller import AbstractController
from bot.rest.utils import try_get

LOG = logging.getLogger(__name__)


class ResetRosterController(AbstractController):
    def __init__(self, reset_roster_service: ResetRosterService):
        super().__init__()
        self._service = reset_roster_service

    def _routes(self):

        @timeout_decorator.timeout(seconds=30)
        @self.api.route("/resetroster", methods=["POST"])
        def _reset_roster():
            body = request.json
            date = try_get(body, "datetime", default=None)
            next_reset: Optional[datetime] = None
            if date is not None:
                next_reset = datetime.fromisoformat(date)
            red = try_get(body, "rbl", default=[])
            green = try_get(body, "gbl", default=[])
            blue = try_get(body, "bbl", default=[])
            ebg = try_get(body, "ebg", default=[])
            LOG.info("Received request to set resetroster %s. RBL: %s GBL: %s, BBL: %s, EBG: %s", next_reset, ", ".join(red), ", ".join(green), ", ".join(blue), ", ".join(ebg))
            res = self._service.set_reset_roster(next_reset, red, green, blue, ebg)
            return "OK" if res == 0 else abort(400, res)
