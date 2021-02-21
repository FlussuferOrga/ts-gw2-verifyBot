import re


def strip_ts_channel_name_tags(channel_name: str) -> str:
    regex = r'^\[.spacer](.+)$'
    match = re.match(regex, channel_name)
    if match:
        group = match.group(1)
        if group:
            return group.strip()
    return channel_name.strip()
