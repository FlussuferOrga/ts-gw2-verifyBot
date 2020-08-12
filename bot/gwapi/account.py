from typing import List, TypedDict


# example https://api.guildwars2.com/v2/account?access_token=564F181A-F0FC-114A-A55D-3C1DCD45F3767AF3848F-AB29-4EBF-9594-F91E6A75E015&lang=en
class Account(TypedDict):
    id: str
    name: str
    age: int
    world: int
    guilds: List[str]
    guild_leader: List[str]
    created: str
    access: List[str]
    commander: bool
    fractal_level: int
    daily_ap: int
    monthly_ap: int
    wvw_rank: int
