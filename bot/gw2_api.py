import gw2api.v2


def get_guild_info(guildname):
    """
    Lookup guild by name. If such a guild exists (and the API is available)
    the info as specified on https://wiki.guildwars2.com/wiki/API:2/guild/:id is returned.
    Else, None is returned.
    """
    guild_ids = gw2api.v2.guild.search(guildname)
    if len(guild_ids) == 0:
        return None
    if len(guild_ids) > 1:
        raise RuntimeError("More than one guild found for name: " + guildname)
    return gw2api.v2.guild.get(guild_ids[0])
