from unittest import TestCase

from bot.emblem_downloader import download_guild_emblem
from bot.util import initialize_logging

ANY_INVALID_GUILD_ID = "abc"
ANY_INVALID_GUILD_NAME = "def"

ANY_VALID_GUILD_ID = "14762DCE-C2A4-E711-80D5-441EA14F1E44"
ANY_VALID_GUILD_NAME = "Lqibzzexgvkikpydotxsvijehyhexd"


class TestEmblemDownloader(TestCase):
    def setUp(self) -> None:
        super().setUp()
        initialize_logging()

    def test__download_guild_emblem_returns_none_on_not_existing_guild(self):
        icon_id, icon_data = download_guild_emblem(ANY_INVALID_GUILD_ID, ANY_INVALID_GUILD_NAME)
        self.assertIsNone(icon_id)
        self.assertIsNone(icon_data)

    def test__download_guild_emblem_returns_on_existing_guild(self):
        icon_id, icon_data = download_guild_emblem(ANY_VALID_GUILD_ID, ANY_VALID_GUILD_NAME)
        self.assertIsNotNone(icon_id)
        self.assertIsNotNone(icon_data)
        self.assertGreater(len(icon_data), 1000)
        self.assertEqual(icon_data[1:4].decode("ascii"), "PNG")  # check image header
