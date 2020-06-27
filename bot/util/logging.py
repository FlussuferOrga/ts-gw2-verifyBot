import logging
import sys

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def initialize(file="./ts3bot.log", level: int = logging.DEBUG):
    formatter = logging.Formatter(FORMAT)

    handlers = []
    for handler, level in [(logging.StreamHandler(sys.stdout), logging.DEBUG), (logging.FileHandler(file, delay=True), logging.DEBUG)]:
        handler.setLevel(level)
        handler.setFormatter(formatter)
        handlers.append(handler)

    logging.basicConfig(
        level=level,
        format=FORMAT,
        handlers=handlers
    )
