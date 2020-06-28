from unittest import TestCase
from unittest.mock import MagicMock

from flask import Flask, Response, json

from bot.rest.controller import GuildController


class TestGuildController(TestCase):
    def setUp(self) -> None:
        super().setUp()

        flask = Flask(__name__)

        self._bot_mock = MagicMock()

        controller = GuildController(self._bot_mock)

        flask.register_blueprint(controller.api)
        self._app = flask.test_client()

    def test_guild_create_returns_ok(self):
        request_data = {
            'name': "Die Dummies",
            'tag': "DDu",
            # 'tsgroup': "",
            'contacts': [
                "User.1234",
                "OtherUser.2345"
            ]
        }

        self._bot_mock.createGuild = MagicMock(return_value=0)

        result: Response = self._app.post(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._bot_mock.createGuild.assert_called_with("Die Dummies", "DDu", "DDu", ["User.1234", "OtherUser.2345"])

        self.assertEqual(200, result.status_code)
        self.assertEqual("OK", result.get_data(as_text=True))

    def test_guild_create_returns_ok_with_custom_tsgroup(self):
        request_data = {
            'name': "Die Dummies",
            'tag': "DDu",
            'tsgroup': "Dumm",
            'contacts': [
                "User.1234",
                "OtherUser.2345"
            ]
        }

        self._bot_mock.createGuild = MagicMock(return_value=0)

        result: Response = self._app.post(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._bot_mock.createGuild.assert_called_with("Die Dummies", "DDu", "Dumm", ["User.1234", "OtherUser.2345"])

        self.assertEqual(200, result.status_code)
        self.assertEqual("OK", result.get_data(as_text=True))

    def test_guild_create_returns_400_on_error(self):
        request_data = {
            'name': "Die Dummies",
            'tag': "DDu",
            # 'tsgroup': "",
            'contacts': [
                "User.1234",
                "OtherUser.2345"
            ]
        }

        self._bot_mock.createGuild = MagicMock(return_value=-123)  # any unexpected return code

        result: Response = self._app.post(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._bot_mock.createGuild.assert_called_with("Die Dummies", "DDu", "DDu", ["User.1234", "OtherUser.2345"])

        self.assertEqual(400, result.status_code)

        result_str = result.get_data(as_text=True)
        self.assertIn("Bad Request", result_str)
        self.assertIn("-123", result_str)

    def test_guild_delete_works(self):
        request_data = {
            'name': "Die Dummies"
        }

        self._bot_mock.removeGuild = MagicMock(return_value=0)  # any unexpected return code

        result: Response = self._app.delete(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._bot_mock.removeGuild.assert_called_with("Die Dummies")

        self.assertEqual(200, result.status_code)
        self.assertEqual("OK", result.get_data(as_text=True))

    def test_guild_delete_returns_400_on_failure(self):
        request_data = {
            'name': "Die Dummies"
        }

        self._bot_mock.removeGuild = MagicMock(return_value=-1)  # any unexpected return code

        result: Response = self._app.delete(
            "/guild",
            data=json.dumps(request_data),
            content_type='application/json'
        )

        self._bot_mock.removeGuild.assert_called_with("Die Dummies")

        self.assertEqual(400, result.status_code)

        result_str = result.get_data(as_text=True)
        self.assertIn("Bad Request", result_str)
        self.assertIn("-1", result_str)
