from unittest import TestCase
from unittest.mock import MagicMock

from flask import Flask, json
from werkzeug.test import TestResponse

import bot
import bot.rest.bootstrap
from bot.rest.controller import GuildController


class TestGuildController(TestCase):
    def setUp(self) -> None:
        super().setUp()

        flask = Flask(__name__)

        self._service_mock = MagicMock()
        self._audit_service_mock = MagicMock()

        controller = GuildController(self._service_mock,self._audit_service_mock)

        flask.register_blueprint(controller.api)
        bot.rest.bootstrap.register_error_handlers(flask)

        self._app = flask.test_client()

    def test_guild_create_returns_ok(self):
        request_data = {
            'name': "Die Dummies",
            # 'tsgroup': "",
            'contacts': [
                "User.1234",
                "OtherUser.2345"
            ]
        }

        self._service_mock.create_guild = MagicMock(return_value=0)

        result: TestResponse = self._app.post(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._service_mock.create_guild.assert_called_with("Die Dummies", None, ["User.1234", "OtherUser.2345"])

        self.assertEqual(200, result.status_code)
        self.assertEqual('"OK"\n', result.get_data(as_text=True))

    def test_guild_create_returns_ok_with_custom_tsgroup(self):
        request_data = {
            'name': "Die Dummies",
            'tsgroup': "Dumm",
            'contacts': [
                "User.1234",
                "OtherUser.2345"
            ]
        }

        self._service_mock.create_guild = MagicMock(return_value=0)

        result: TestResponse = self._app.post(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._service_mock.create_guild.assert_called_with("Die Dummies", "Dumm", ["User.1234", "OtherUser.2345"])

        self.assertEqual(200, result.status_code)
        self.assertEqual('"OK"\n', result.get_data(as_text=True))

    def test_guild_create_returns_400_on_error(self):
        request_data = {
            'name': "Die Dummies",
            # 'tsgroup': "",
            'contacts': [
                "User.1234",
                "OtherUser.2345"
            ]
        }

        self._service_mock.create_guild = MagicMock(return_value=-123)  # any unexpected return code

        result: TestResponse = self._app.post(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._service_mock.create_guild.assert_called_with("Die Dummies", None, ["User.1234", "OtherUser.2345"])

        self.assertEqual(400, result.status_code)

        result_str = result.get_data(as_text=True)
        data = json.loads(result_str)
        self.assertEqual(data["code"], 400)
        self.assertEqual(data["name"], "Bad Request")
        self.assertEqual(data["desc"], "Operation was not successful. Response code: -123")

    def test_guild_delete_works(self):
        request_data = {
            'name': "Die Dummies"
        }

        self._service_mock.remove_guild = MagicMock(return_value=0)  # any unexpected return code

        result: TestResponse = self._app.delete(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._service_mock.remove_guild.assert_called_with("Die Dummies")

        self.assertEqual(200, result.status_code)
        self.assertEqual('"OK"\n', result.get_data(as_text=True))

    def test_guild_delete_returns_400_on_failure(self):
        request_data = {
            'name': "Die Dummies"
        }

        self._service_mock.remove_guild = MagicMock(return_value=-1)  # any unexpected return code

        result: TestResponse = self._app.delete(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._service_mock.remove_guild.assert_called_with("Die Dummies")

        self.assertEqual(400, result.status_code)

        result_str = result.get_data(as_text=True)
        self.assertIn("Bad Request", result_str)
        self.assertIn("-1", result_str)
