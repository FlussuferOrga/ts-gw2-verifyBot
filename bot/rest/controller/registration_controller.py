import logging

from flask import request
from timeout_decorator import timeout_decorator

from bot import UserService
from bot.rest.controller.abstract_controller import AbstractController
from bot.rest.utils import try_get

LOG = logging.getLogger(__name__)


class RegistrationController(AbstractController):
    def __init__(self, user_service: UserService):
        super().__init__()
        self._user_service = user_service

    def _routes(self):

        @timeout_decorator.timeout(seconds=30)
        @self.api.route("/registration", methods=["DELETE"])
        def _delete_registration():
            body = request.json
            gw2account = try_get(body, "gw2account", default="")
            LOG.info("Received request to delete user '%s' from the TS registration database.", gw2account)
            changes = self._user_service.delete_registration(gw2account)
            return {"changes": changes}
