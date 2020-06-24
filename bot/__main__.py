import logging
import sys

from bot.Main import main
from bot.util.Logging import initialize_logging

LOG = logging.getLogger(__name__)

if __name__ == '__main__':
    initialize_logging()
    main(sys.argv[1:])
