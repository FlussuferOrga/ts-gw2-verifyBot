import logging

from flask import jsonify, request

from bot import AuditService, UserService
from bot.rest.controller.abstract_controller import AbstractController
from bot.rest.utils import try_get

LOG = logging.getLogger(__name__)


class RegistrationController(AbstractController):
    def __init__(self, user_service: UserService, audit_service: AuditService):
        super().__init__()
        self._user_service = user_service
        self._audit_service = audit_service

    def _routes(self):
        @self.api.route("/registration", methods=["DELETE"])
        def _delete_registration():
            body = request.json
            gw2account = try_get(body, "gw2account", default="")
            LOG.info("Received request to delete user '%s' from the TS registration database.", gw2account)
            changes = self._user_service.delete_registration(gw2account)
            return {"changes": changes}

        @self.api.route("/registration/_audit", methods=["POST"])
        def _trigger_audit():
            LOG.info("Received request to audit")
            self._audit_service.trigger_user_audit()
            return jsonify("Triggered")
