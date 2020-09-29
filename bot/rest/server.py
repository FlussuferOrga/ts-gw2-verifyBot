import logging
import threading

import flask_cors
import waitress  # productive serve
from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

from bot.rest.controller import GuildController, HealthController, OtherController, ResetRosterController
from bot.rest.utils import error_response

LOG = logging.getLogger(__name__)


class HTTPServer(Flask):
    def __init__(self, bot, port):
        super().__init__(__name__,
                         static_url_path='',
                         static_folder="dist/static",
                         template_folder="dist/templates")
        self.bot = bot
        self.port = port
        self._thread = self._create_thread()

    def start(self):
        LOG.debug("Starting HTTP Server...")
        self._thread.setDaemon(True)
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

    register_controllers(app, bot)
    register_error_handlers(flask=app)

    register_open_api_endpoints(app)

    return app


def register_open_api_endpoints(app):
    @app.route('/')
    def _dist():
        return render_template('index.html', swagger_ui_version="3.34.0")

    @app.route('/v2/api-docs')
    def _dist2():
        return app.send_static_file('openapi-spec.yaml')


def register_controllers(app, bot):
    controller = [
        HealthController(),
        GuildController(bot.guild_service),
        ResetRosterController(bot),
        OtherController(bot.user_service, bot.commander_service),
    ]
    for ctrl in controller:
        app.register_blueprint(ctrl.api)


def register_error_handlers(flask: Flask):
    @flask.errorhandler(HTTPException)
    def _handle_error(exception: HTTPException):
        return error_response(exception.code, exception.name, exception.description)
