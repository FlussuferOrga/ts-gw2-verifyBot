from typing import List, TypedDict


class EmblemData(TypedDict):
    id: int
    colors: List[int]


class Emblem(TypedDict):
    background: EmblemData
    foreground: EmblemData
    flags: List[str]

class AnonymousGuild(TypedDict):
    id: str
    name: str
    tag: str
    emblem: Emblem


class Guild(AnonymousGuild):
    level: int
    motd: str
    influence: int
    aetherium: int
    resonance: int
    favor: int
    member_count: int
    member_capacity: int
