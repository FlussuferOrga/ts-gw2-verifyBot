from typing import TypedDict


class AnonymousGuild(TypedDict):
    id: str
    name: str
    tag: str
    # emblem:


class Guild(AnonymousGuild):
    level: int
    motd: str
    influence: int
    aetherium: int
    resonance: int
    favor: int
    member_count: int
    member_capacity: int
