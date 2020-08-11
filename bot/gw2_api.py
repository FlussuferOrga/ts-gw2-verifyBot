from typing import List

from gw2api import GuildWars2Client


# Available api endpoints:
#     account, accountachievements, accountbank, accountdungeons, accountdyes,
#     accountfinishers, accountgliders, accounthomecats, accounthomenodes, accountinventory,
#     accountmailcarriers, accountmasteries, accountmasterypoints, accountmaterials, accountminis,
#     accountoutfits, accountpvpheroes, accountraids, accountrecipes, accountskins,
#     accounttitles, accountwallet, achievements, achievementscategories, achievementsdaily,
#     achievementsdailytomorrow, achievementsgroups, backstoryanswers, backstoryquestions,
#     build, cats, characters, colors, commercedelivery,
#     commerceexchange, commerceexchangecoins, commerceexchangegems,
#     commercelistings, commerceprices, commercetransactions, continents,
#     currencies, dungeons, emblem, files, finishers, gliders,
#     guildid, guildidlog, guildidmembers, guildidranks, guildidstash,
#     guildidteams, guildidtreasury, guildidupgrades, guildpermissions,
#     guildsearch, guildupgrades, items, itemstats, lang, legends,
#     mailcarriers, maps, masteries, materials, minis, nodes,
#     outfits, pets, professions, proxy, pvp, pvpamulets, pvpgames,
#     pvpheroes, pvpranks, pvpseasons, pvpseasonsleaderboards, pvpstandings,
#     pvpstats, quaggans, races, raids, recipes, recipessearch, session,
#     skills, skins, specializations, stories, storiesseasons, titles,
#     tokeninfo, traits, version, worlds, wvw, wvwabilities,
#     wvwmatches, wvwmatchesstatsteams, wvwobjectives, wvwranks, wvwupgrades
#


def _create_client(api_key: str = None) -> GuildWars2Client:
    return GuildWars2Client(version='v2', api_key=api_key)


_anonymousClient = _create_client()  # this client can be reused, to save initialization time for non-api-key requests


def guild_get(guild_id: str):
    if guild_id is None:
        return None
    result = _anonymousClient.guildid.get(guild_id)
    return _check_error(result)


def _check_error(result):
    if "text" in result:
        raise ApiError(result["text"])
    return result


def guild_search(guild_name: str):
    search_result = _anonymousClient.guildsearch.get(name=guild_name)
    search_result = _check_error(search_result)
    if len(search_result) == 0:
        return None
    if len(search_result) > 1:
        raise ApiError("More than one guild found for name: " + guild_name)
    return search_result[0]


def account_get(api_key: str):
    api = _create_client(api_key=api_key)
    return _check_error(api.account.get())


def characters_get(api_key: str):
    api = _create_client(api_key=api_key)
    return _check_error(api.characters.get(page="0", page_size=200))


def worlds_get(ids: List[int] = None):
    return _check_error(_anonymousClient.worlds.get(ids=ids))


def worlds_get_one(world_id: int = None):
    return worlds_get([world_id])[0]


class ApiError(RuntimeError):
    pass
