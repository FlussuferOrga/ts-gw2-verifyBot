import logging
import inspect


def getLogger(name = None, file = "ts3bot.log", level = logging.DEBUG, generate_name = True):
    '''
    Retrieves a specific logger with fixed configuration.
    The philosophy behind logging is explained in https://docs.python.org/3/howto/logging.html
    To avoid a bit of boiler place code and setup, this method
    creates the requested logger to log WARNINGs and above to the console and
    additionally everything from DEBUG up to a file.
    It is still recommended to create one logger per module once at the top
    and also to set the level parameter from a config file; see parameter
    documentation for details.

    name: name of the logger. This can be omitted and will default to the name 
            of the calling module or "root", if called from the main module.
    file: the file messages with DEBUG and above level are logged to. 
            Defaults to ts3bot.log
    level: the global level for the logger. While two handlers exist for
            printing to console and to file with their own level, 
            the logger itself can be set to a certain log level (default: DEBUG)
            which can disable messages before reaching the respective handler,
            see https://docs.python.org/3/_images/logging_flow.png
            Setting this to something above DEBUG can help when dealing with 
            excessive log output.
    generate_name: Automatically generates a name for the logger based on the calling module if name is not given.
    '''
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if not name and generate_name:
        try:
            frame = inspect.stack()[1]
            name = inspect.getmodule(frame[0]).__name__
        except:
            name = "ROOT"

    logger = logging.getLogger(name)

    if not logger.hasHandlers():
        # initialize handlers
        logger.setLevel(level)
        for h,l in ((logging.StreamHandler(), logging.WARNING), (logging.FileHandler(file), logging.DEBUG)):
            h.setLevel(l)
            h.setFormatter(formatter)
            logger.addHandler(h)  

    return logger

# set default logger to the log file
# this also provides logging messages from other modules i.e. ts3.
getLogger(generate_name=False) 
