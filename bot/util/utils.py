import re


def strip_ts_channel_name_tags(channel_name: str) -> str:
    regex = r'^\[.spacer](.+)$'
    return re.match(regex, channel_name).group(1).strip() or channel_name.strip()
