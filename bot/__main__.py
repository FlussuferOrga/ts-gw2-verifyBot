import logging

from bot.main import main
from bot.util import initialize_logging

LOG = logging.getLogger(__name__)


def startup():
    initialize_logging()
    main()


if __name__ == '__main__':
    startup()
