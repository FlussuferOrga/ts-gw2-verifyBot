from typing import TypedDict


# example https://api.guildwars2.com/v2/characters?page=0&page_size=200&access_token=564F181A-F0FC-114A-A55D-3C1DCD45F3767AF3848F-AB29-4EBF-9594-F91E6A75E015&lang=en
class Character(TypedDict):
    name: str
    race: str
    gender: str
    profession: str
    level: int
    guild: str
    age: int
    created: str
    # much more
