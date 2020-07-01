import logging
import sys

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def initialize_logging(file="./ts3bot.log", level: int = logging.DEBUG):
    formatter = logging.Formatter(FORMAT)

    handlers = []
    for handler, handler_level in [(logging.StreamHandler(sys.stdout), logging.DEBUG), (logging.FileHandler(file, delay=True), logging.DEBUG)]:
        handler.setLevel(handler_level)
        handler.setFormatter(formatter)
        handlers.append(handler)

    # noinspection PyArgumentList
    logging.basicConfig(
        level=level,
        format=FORMAT,
        handlers=handlers
    )
