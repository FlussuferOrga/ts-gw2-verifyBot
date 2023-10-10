import logging
from functools import wraps
from typing import Callable, List, Optional

from cachetools import LRUCache, TTLCache, cached
from gw2api import GuildWars2Client
from requests import HTTPError

from .account import Account
from .character import Character
from .guild import AnonymousGuild, Guild
from .world import World

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
LOG = logging.getLogger(__name__)


@cached(cache=TTLCache(maxsize=32, ttl=300))  # cache user specific clients for 5 min - creation takes quite long
def _create_client(api_key: str = None) -> GuildWars2Client:
    return GuildWars2Client(version='v2', api_key=api_key)


_anonymousClient = _create_client()  # this client can be reused, to save initialization time for non-api-key requests


class ApiError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class ApiUnavailableError(ApiError):
    pass


class ApiKeyInvalidError(ApiError):
    pass


def error_checked(decorator):
    @wraps(decorator)
    def wrapper(*args, **kw):
        try:
            if len(args) == 1 and not kw and callable(args[0]):
                result = decorator()(args[0])
            else:
                result = decorator(*args, **kw)
        except HTTPError as e:
            status_code = e.response.status_code
            json = e.response.json()
            if json is not None and "text" in json:
                error_text = json["text"]
                if error_text == "Invalid access token":
                    raise ApiKeyInvalidError(error_text)
                if error_text == "too many requests":
                    raise ApiUnavailableError("Rate Limited")
                if error_text == "ErrTimeout":  # happens on login server down
                    raise ApiUnavailableError(error_text)
                if error_text == "ErrInternal":
                    raise ApiUnavailableError(error_text)
                if error_text == "invalid key" or error_text == "Invalid access token":  # when key is invalid or not a key at all
                    raise ApiKeyInvalidError(error_text)
                LOG.warning("API Returned Error %s - %s", status_code, error_text)
                raise ApiError(str(status_code) + ":" + error_text) from e
            LOG.warning("API Returned %s - %s", status_code, e.response.text)
            raise ApiError("Unknown API Error") from e
        # if result:
        #     _check_error(result)
        return result

    return wrapper


@cached(cache=TTLCache(maxsize=20, ttl=60 * 60))  # cache for 1h
@error_checked
def guild_get(guild_id: str) -> Optional[AnonymousGuild]:
    return _anonymousClient.guildid.get(guild_id)


@cached(cache=TTLCache(maxsize=10, ttl=300))  # cache clients for 5 min - creation takes quite long
@error_checked
def guild_get_full(api_key: str, guild_id: str) -> Optional[Guild]:
    api = _create_client(api_key=api_key)
    return api.guildid.get(guild_id)


@error_checked
def guild_search_internal(guild_name: str) -> Optional[str]:
    return _anonymousClient.guildsearch.get(name=guild_name)


@cached(cache=TTLCache(maxsize=32, ttl=600))  # cache for 10 min
def guild_search(guild_name: str) -> Optional[str]:
    search_result = guild_search_internal(guild_name)
    if len(search_result) == 0:
        return None
    if len(search_result) > 1:
        raise ApiError("More than one guild found for name: " + guild_name)
    return search_result[0]


@cached(cache=TTLCache(maxsize=32, ttl=300))  # cache clients for 5 min - creation takes quite long
@error_checked
def account_get(api_key: str) -> Account:
    api = _create_client(api_key=api_key)
    return api.account.get()


@cached(cache=TTLCache(maxsize=32, ttl=300))  # cache clients for 5 min - creation takes quite long
@error_checked
def characters_get(api_key: str) -> List[Character]:
    api = _create_client(api_key=api_key)
    return api.characters.get(page="0", page_size=200)


@cached(cache=LRUCache(maxsize=10))
@error_checked
def worlds_get_ids() -> List[int]:
    return _anonymousClient.worlds.get(ids=None)


@error_checked
def worlds_get_by_ids(ids: List[int]) -> List[World]:
    return _anonymousClient.worlds.get(ids=ids)


@cached(cache=LRUCache(maxsize=10))
@error_checked
def worlds_get_one(world_id: int = None) -> Optional[World]:
    worlds = worlds_get_by_ids([world_id])
    if len(worlds) == 1:
        return worlds[0]
    return None
