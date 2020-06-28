import logging
import threading

import waitress  # productive serve
from flask import Flask

from bot.rest.controller import GuildController, HealthController, OtherController

LOG = logging.getLogger(__name__)


class HTTPServer(Flask):
    def __init__(self, bot, port):
        super().__init__(__name__)
        self.bot = bot
        self.port = port
        self._thread = self._create_Thread()

    def start(self):
        LOG.debug("Starting HTTP Server...")
        self._thread.start()

    def _create_Thread(self):
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

    controller = [
        HealthController(),
        GuildController(bot),
        OtherController(bot)
    ]

    for ctrl in controller:
        app.register_blueprint(ctrl.api)
    return app
