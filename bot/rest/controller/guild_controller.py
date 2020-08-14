import logging

from flask import jsonify, request
from werkzeug.exceptions import BadRequest

from bot import GuildService
from bot.rest.controller.abstract_controller import AbstractController
from bot.rest.utils import try_get

LOG = logging.getLogger(__name__)


class GuildController(AbstractController):
    def __init__(self, guild_service: GuildService):
        super().__init__()
        self._service = guild_service

    @staticmethod
    def validate_name(name):
        if name is None:
            raise BadRequest("Property $.name is required")
        if not name.strip():  # check for blank name
            raise BadRequest("Property $.name can not be empty")

    def _routes(self):

        @self.api.route("/guild", methods=["POST"])
        def _create_guild():
            name = try_get(request.json, "name", default=None)
            group_name = try_get(request.json, "tsgroup", default=None)
            contacts = try_get(request.json, "contacts", default=[])

            self.validate_name(name)

            LOG.info("Received request to create guild %s (Group %s) with contacts %s", name, group_name, ", ".join(contacts))

            res = self._service.create_guild(name, group_name, contacts)

            if res == 0:
                return jsonify("OK")
            else:
                raise BadRequest(f"Operation was not successful. Response code: {res}")

        @self.api.route("/guild", methods=["DELETE"])
        def _delete_guild():
            name = try_get(request.json, "name", default=None)
            self.validate_name(name)

            LOG.info("Received request to delete guild %s", name)

            res = self._service.remove_guild(name)
            if res == 0:
                return jsonify("OK")
            else:
                raise BadRequest(f"Operation was not successful. Response code: {res}")
