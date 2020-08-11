import logging

from flask import jsonify, request
from werkzeug.exceptions import BadRequest, abort

from bot import Bot
from bot.rest.controller.abstract_controller import AbstractController
from bot.rest.utils import try_get

LOG = logging.getLogger(__name__)


class GuildController(AbstractController):
    def __init__(self, bot: Bot):
        super().__init__()
        self._bot = bot

    def _routes(self):
        @self.api.route("/guild", methods=["POST"])
        def _create_guild():
            body = request.json
            name = try_get(body, "name", default=None)
            tag = try_get(body, "tag", default=None)
            groupname = try_get(body, "tsgroup", default=tag)
            contacts = try_get(body, "contacts", default=[])

            LOG.info("Received request to create guild %s [%s] (Group %s) with contacts %s", name, tag, groupname, ", ".join(contacts))

            if name is None:
                raise BadRequest("Property $.name is required")
            if tag is None:
                raise BadRequest("Property $.tag is required")

            res = self._bot.createGuild(name, tag, groupname, contacts)

            if res == 0:
                return jsonify("OK")
            else:
                raise BadRequest(f"Operation was not successful. Response code: {res}")
        @self.api.route("/guild", methods=["DELETE"])
        def _delete_guild():
            body = request.json
            name = try_get(body, "name", default=None)
            tag = try_get(body, "tag", default=None)

            LOG.info("Received request to delete guild %s", name)

            res = self._bot.removeGuild(name, tag)
            return jsonify("OK") if res == 0 else abort(400, f"Operation was not successful. Response code: {res}")
