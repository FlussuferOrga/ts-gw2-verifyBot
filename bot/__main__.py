import logging

from bot.main import main, parse_args
from bot.util import initialize_logging

LOG = logging.getLogger(__name__)


def startup():
    config, parser = parse_args()

    initialize_logging(config.logging_file, config.logging_level)

    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug("Config Sources:\n%s", parser.format_values())

    main(config)


if __name__ == '__main__':
    startup()
