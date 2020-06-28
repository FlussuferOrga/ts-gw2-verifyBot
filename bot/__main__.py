import logging

from bot.main import main
from bot.util import initialize_logging

LOG = logging.getLogger(__name__)

if __name__ == '__main__':
    initialize_logging()
    main()
