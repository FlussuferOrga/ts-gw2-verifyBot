class LazySingleton:
    class __OnlyOne:
        def __str__(self):
            return repr(self)

    instance = None

    def __init__(self):
        if not LazySingleton.instance:
            LazySingleton.instance = LazySingleton.__OnlyOne()

    def __getattr__(self, name):
        return getattr(self.instance, name)
