import flask_cors
from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

from bot.rest.controller import \
    CommandersController, GuildController, HealthController, RegistrationController, ResetRosterController
from bot.rest.server import HTTPServer
from bot.rest.utils import error_response


def create_http_server(bot, port=8080):
    app = HTTPServer(bot, port)
    flask_cors.CORS(app)

    register_controller(app, bot)
    register_error_handlers(flask=app)

    register_open_api_endpoints(app)
    return app


def register_open_api_endpoints(app):
    @app.route('/')
    def _dist():
        return render_template('index.html', swagger_ui_version="3.48.0")

    @app.route('/v2/api-docs')
    def _dist2():
        return app.send_static_file('openapi-spec.yaml')


def register_controller(app, bot):
    controller = [
        HealthController(),
        GuildController(bot.guild_service),
        ResetRosterController(bot.reset_roster_service),
        RegistrationController(bot.user_service),
        CommandersController(bot.commander_service)
    ]
    for ctrl in controller:
        app.register_blueprint(ctrl.api)


def register_error_handlers(flask: Flask):
    @flask.errorhandler(HTTPException)
    def _handle_error(exception: HTTPException):
        return error_response(exception.code, exception.name, exception.description)
