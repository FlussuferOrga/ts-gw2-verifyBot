import logging
import threading

import flask_cors
import waitress  # productive serve
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from bot.rest.controller import GuildController, HealthController, OtherController, ResetRosterController

LOG = logging.getLogger(__name__)


class HTTPServer(Flask):
    def __init__(self, bot, port):
        super().__init__(__name__)
        self.bot = bot
        self.port = port
        self._thread = self._create_thread()

    def start(self):
        LOG.debug("Starting HTTP Server...")
        self._thread.start()

    def _create_thread(self):
        # weirdly, specifying the host parameter results in the initial boot message of
        # waitress being posted twice. I am not sure if the routes are also set twice,
        # but other users have reported this behavior as well, so I not taking any chances here.
        # https://stackoverflow.com/a/57074705
        thread = threading.Thread(target=waitress.serve, kwargs={"app": self, "port": self.port})
        thread.daemon = True
        return thread

    def stop(self):
        # LOG.debug("Stopping HTTP Server...")
        pass  # fixme: stop waitress


def create_http_server(bot, port=8080):
    app = HTTPServer(bot, port)
    flask_cors.CORS(app)
    controller = [
        HealthController(),
        GuildController(bot),
        ResetRosterController(bot),
        OtherController(bot),
    ]

    for ctrl in controller:
        app.register_blueprint(ctrl.api)

    @app.errorhandler(HTTPException)
    def _not_found(e: HTTPException):
        return jsonify(code=e.code, name=e.name, desc=e.description), e.code

    return app
