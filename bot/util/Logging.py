import logging
import sys


def initialize_logging(file="./ts3bot.log", level=logging.DEBUG):
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    handlers = []
    for h, l in (
            (logging.StreamHandler(sys.stdout), logging.DEBUG),
            (logging.FileHandler(file, delay=True), logging.DEBUG)):
        h.setLevel(l)
        h.setFormatter(formatter)
        handlers.append(h)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers
    )
