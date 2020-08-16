from typing import TypedDict


class ChannelListDetail(TypedDict):
    cid: str
    pid: str
    channel_order: str
    channel_name: str
    total_clients: str
    channel_needed_subscribe_power: str
