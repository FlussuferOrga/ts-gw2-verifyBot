import logging
from typing import Optional, Union

import sys

FORMAT = "%(asctime)s %(levelname)-6s [%(threadName)s] %(name)s: %(message)s"

_nameToLevel = {
    'CRITICAL': logging.CRITICAL,
    'FATAL': logging.FATAL,
    'ERROR': logging.ERROR,
    'WARN': logging.WARNING,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG
}


def _level_from_name(level: Union[str, int]) -> int:
    result = _nameToLevel.get(level)
    if result is not None:
        return result
    return level


def initialize_logging(file: Optional[str] = "./ts3bot.log", level: Union[str, int] = logging.DEBUG):
    level = _level_from_name(level)

    formatter = logging.Formatter(FORMAT)

    handlers = [logging.StreamHandler(sys.stdout)]
    if file is not None:
        handlers.append(logging.FileHandler(file, delay=True, encoding='utf-8'))

    for handler in handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)

    # noinspection PyArgumentList
    logging.basicConfig(
        level=level,
        format=FORMAT,
        handlers=handlers
    )

    # SSH Log is very verbose on DEBUG
    logging.getLogger("paramiko.transport").setLevel(logging.INFO)
