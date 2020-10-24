import logging

LOG = logging.getLogger(__name__)


class Locale:
    def __init__(self, fallback=None):
        self._fallback = fallback
        self._values = {}

    def get(self, key, args=()):
        """
        key: the string to identify the locale-string with
        args: an optional tuple of arguments to pass to the old style formatter. If the number of arguments don't match the number of template spots in the string, no argument will be inserted at all
        returns: either the looked-up locale-string, the loooked-up locale from the fallback Locale (if any) or the key as fallback-fallback
        """
        if key in self._values:
            tpl = self._values[key]
        elif self._fallback is not None:
            tpl = self._fallback.get(key)
        else:
            tpl = key
        try:
            tpl = tpl % args
        except TypeError:
            LOG.error("Could not insert all %d arguments into the string with key '%s' of locale %s. I will not insert any arguments at all.", len(args), key, self.__class__.__name__)
        return tpl

    def set(self, key, value):
        self._values[key] = value


class MultiLocale(Locale):
    def __init__(self, locales, glue="\n\n-------------------------------------\n\n"):
        super().__init__()
        self._locales = locales
        self._glue = glue

    def get(self, key, args=()):
        return self._glue.join([locale.get(key, args) for locale in self._locales])
