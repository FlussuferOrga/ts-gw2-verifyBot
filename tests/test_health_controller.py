from unittest import TestCase

from flask import Flask
from werkzeug.test import TestResponse

from bot.rest.controller import HealthController


class TestHealthController(TestCase):
    def setUp(self) -> None:
        super().setUp()
        flask = Flask(__name__)
        flask.register_blueprint(HealthController().api)
        self._app = flask.test_client()

    def test_health_check_returns_ok(self):
        result: TestResponse = self._app.get("/health")
        self.assertEqual(200, result.status_code)
        self.assertEqual("OK", result.get_data(as_text=True))
