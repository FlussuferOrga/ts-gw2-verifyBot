import logging
import sys

from bot.main import main
from bot.util.logging import initialize

LOG = logging.getLogger(__name__)

if __name__ == '__main__':
    initialize()
    main(sys.argv[1:])
