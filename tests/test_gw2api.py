from unittest import TestCase

import sys

import bot.gwapi as gw2api


class Gw2ApiFacadeTest(TestCase):
    # From https://status.gw2efficiency.com/
    TEST_TOKEN = "564F181A-F0FC-114A-A55D-3C1DCD45F3767AF3848F-AB29-4EBF-9594-F91E6A75E015"

    # suppress warnings only occurring in pytest -> https://stackoverflow.com/a/56381855/3757624
    def setUp(self):
        if not sys.warnoptions:
            import warnings
            warnings.simplefilter("ignore")

    def test_guild_search(self):
        guild_id = gw2api.guild_search("Lqibzzexgvkikpydotxsvijehyhexd")
        self.assertEqual(guild_id, "14762DCE-C2A4-E711-80D5-441EA14F1E44")

    def test_guild_search_no_result(self):
        guild_id = gw2api.guild_search("aadafddfggfadasd")
        self.assertIsNone(guild_id)

    def test_get_guild_info(self):
        guild_info = gw2api.guild_get("14762DCE-C2A4-E711-80D5-441EA14F1E44")
        self.assertEqual(guild_info["tag"], "LQIb")
        self.assertEqual(guild_info["name"], "Lqibzzexgvkikpydotxsvijehyhexd")

    def test_get_guild_info_wrong_id(self):
        with self.assertRaises(gw2api.ApiError):
            gw2api.guild_get("bad-id-that-is-made-up")

    def test_get_account_info(self):
        account_info = gw2api.account_get(self.TEST_TOKEN)
        self.assertEqual(account_info["id"], "0B595DDF-5DA2-E711-80C3-ECB1D78A5C75")
        self.assertEqual(account_info["name"], "efficiencytesting.3518")
        self.assertEqual(account_info["world"], 2013)
        self.assertEqual(account_info["guilds"], ["14762DCE-C2A4-E711-80D5-441EA14F1E44"])
        self.assertEqual(account_info["guild_leader"], ["14762DCE-C2A4-E711-80D5-441EA14F1E44"])
        self.assertEqual(account_info["created"], "2017-09-26T01:57:00Z")
        self.assertFalse(account_info["commander"])

    def test_get_account_info_bad_key(self):
        with self.assertRaises(gw2api.ApiError, msg="Invalid access token"):
            gw2api.account_get("qdasdasd-asdasd-as-d-asd-a-sd")

    def test_get_characters(self):
        characters = gw2api.characters_get(self.TEST_TOKEN)
        self.assertEqual(len(characters), 2)
        self.assertListEqual(list(map(lambda x: x.get("level"), characters)), [23, 12])
        self.assertListEqual(list(map(lambda x: x.get("name"), characters)), ["Eff Testing Warr", "Eff Testing Ele"])

    def test_get_worlds(self):
        worlds = gw2api.worlds_get_ids()
        self.assertTrue(1004 in worlds)
        self.assertTrue(2202 in worlds)
        self.assertTrue(2010 in worlds)

    def test_get_worlds_by_ids(self):
        worlds = gw2api.worlds_get_by_ids(ids=[2202])
        self.assertEqual(len(worlds), 1)
        self.assertEqual(worlds[0]["id"], 2202)
        self.assertEqual(worlds[0]["name"], "Riverside [DE]")
        self.assertIsNotNone(worlds[0]["population"])

    def test_get_one_world_by_id(self):
        world = gw2api.worlds_get_one(2202)
        self.assertEqual(world["id"], 2202)
        self.assertEqual(world["name"], "Riverside [DE]")
        self.assertIsNotNone(world["population"])
