from unittest import TestCase
from unittest.mock import MagicMock, PropertyMock

from ts3.query import TS3QueryError

from TS3Repository import TS3Repository


class TestTS3Repository(TestCase):
    def test_send_text_message_to_client_calls_ts3exec(self):
        ts3_connection_mock = MagicMock()
        repo = TS3Repository(ts3_connection_mock)

        repo.send_text_message_to_client(3, "test")

        ts3_connection_mock.ts3exec.assert_called_once()  # TODO: we can not check for the parameters because it is a lambda

    def test_send_text_message_to_server_calls_ts3exec(self):
        ts3_connection_mock = MagicMock()
        repo = TS3Repository(ts3_connection_mock)

        repo.send_text_message_to_server("test")

        ts3_connection_mock.ts3exec.assert_called_once()  # TODO: we can not check for the parameters because it is a lambda

    def test_send_text_message_to_channel_calls_ts3exec(self):
        ts3_connection_mock = MagicMock()
        repo = TS3Repository(ts3_connection_mock)

        repo.send_text_message_to_current_channel("test")

        ts3_connection_mock.ts3exec.assert_called_once()  # TODO: we can not check for the parameters because it is a lambda

    def test_find_channel_calls_ts3exec(self):
        ts3_connection_mock = MagicMock()
        ts3_connection_mock.ts3exec = MagicMock(return_value=[{
            "cid": "42",
            "channel_name": "I am channel test123 !"
        }, None])

        repo = TS3Repository(ts3_connection_mock)

        result = repo.channel_find("test123")

        ts3_connection_mock.ts3exec.assert_called_once()  # TODO: we can not check for the parameters because it is a lambda
        self.assertEqual(result.channel_id, "42")
        self.assertEqual(result.channel_name, "I am channel test123 !")

    def test_find_channel_calls_ts3exec_noresult_returns_none(self):
        query_error = MagicMock()
        query_error.resp = PropertyMock()
        query_error.resp.error = {"id": '768'}

        ts3_connection_mock = MagicMock()
        ts3_connection_mock.ts3exec = MagicMock(return_value=[None, query_error])

        repo = TS3Repository(ts3_connection_mock)

        result = repo.channel_find("test123")

        ts3_connection_mock.ts3exec.assert_called_once()  # TODO: we can not check for the parameters because it is a lambda
        self.assertIsNone(result)

    def test_find_channel_calls_ts3exec_other_exception_raised(self):
        ts3_connection_mock = MagicMock()
        any_exception = RuntimeError("Something else went wrong")
        ts3_connection_mock.ts3exec = MagicMock(return_value=[None, any_exception])

        repo = TS3Repository(ts3_connection_mock)

        with self.assertRaises(RuntimeError):
            repo.channel_find("test123")
        ts3_connection_mock.ts3exec.assert_called_once()  # TODO: we can not check for the parameters because it is a lambda

    def test_find_channel_calls_ts3exec_other_error_reraised(self):
        query_error = TS3QueryError(PropertyMock())
        query_error.resp.error = {"id": '42'}

        ts3_connection_mock = MagicMock()
        ts3_connection_mock.ts3exec = MagicMock(return_value=[None, query_error])

        repo = TS3Repository(ts3_connection_mock)

        with self.assertRaises(TS3QueryError):
            repo.channel_find("test123")

        ts3_connection_mock.ts3exec.assert_called_once()  # TODO: we can not check for the parameters because it is a lambda
