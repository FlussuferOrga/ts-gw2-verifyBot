# Bot Messages
import logging

from bot.messages.english import English
from bot.messages.german import German
from bot.messages.locale import Locale, MultiLocale

LOG = logging.getLogger(__name__)


def get_locale(locale="EN") -> Locale:
    locale = locale.upper()
    locales = locale.split("+")

    if len(locales) > 1:
        return MultiLocale([get_locale(locale) for locale in locales])

    if locale == "DE":
        return German()
    elif locale == "EN":
        return English()
    else:
        LOG.warning("No locale defined, using fallback: English")
        return English()  # catchall
