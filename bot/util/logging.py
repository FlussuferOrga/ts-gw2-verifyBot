import logging
import os
from typing import Optional, Union

import coloredlogs
import sys
from humanfriendly.compat import coerce_string, on_windows
from humanfriendly.terminal import ansi_wrap, enable_ansi_support, terminal_supports_colors

FORMAT_CONSOLE = "%(asctime)s.%(msecs)03d %(levelname)-17s [%(threadName)-10s] %(name)s: %(message)s"
FORMAT_FILE = "%(asctime)s.%(msecs)03d %(levelname)-6s [%(threadName)s] %(name)s: %(message)s"

_nameToLevel = {
    'CRITICAL': logging.CRITICAL,
    'FATAL': logging.FATAL,
    'ERROR': logging.ERROR,
    'WARN': logging.WARNING,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG
}


def _level_from_name(level: Union[str, int]) -> int:
    result = _nameToLevel.get(level)
    if result is not None:
        return result
    return level


def initialize_logging(file: Optional[str] = None, level: Union[str, int] = logging.DEBUG):
    level = _level_from_name(level)

    handlers = []

    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = create_console_formatter()
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    if file is not None:
        file_handler = logging.FileHandler(file, delay=True, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(FORMAT_FILE))
        handlers.append(file_handler)

    for handler in handlers:
        handler.setLevel(level)

    # noinspection PyArgumentList
    logging.basicConfig(level=level, handlers=handlers, format=FORMAT_FILE)

    # SSH Log is very verbose on DEBUG
    logging.getLogger("paramiko.transport").setLevel(logging.INFO)
    logging.getLogger("ts3.query").setLevel(logging.INFO)


# from coloredlogs.install()
def use_color():
    use_colors = True
    if use_colors or (use_colors is None):
        # Respect the user's choice not to have colors.
        if use_colors is None and 'NO_COLOR' in os.environ:
            # For details on this see https://no-color.org/.
            use_colors = False
        # Try to enable Windows native ANSI support or Colorama?
        if (use_colors or use_colors is None) and on_windows():
            # This can fail, in which case ANSI escape sequences would end
            # up being printed to the terminal in raw form. This is very
            # user hostile, so to avoid this happening we disable color
            # support on failure.
            use_colors = enable_ansi_support()
        # When auto detection is enabled, and so far we encountered no
        # reason to disable color support, then we will enable color
        # support if 'stream' is connected to a terminal.
        if use_colors is None:
            use_colors = terminal_supports_colors()

    return use_colors


def create_console_formatter():
    if use_color():
        field_styles = {
            'levelname': {'color': 'black'},
            'name': {'color': 'blue'},
            'threadName': {'color': 'white', 'faint': True}}
        level_styles = {
            'debug': {'color': 'green'},
            'info': {'color': 'blue'},
            'warning': {'color': 'yellow'},
            'error': {'color': 'red', 'bold': True},
            'critical': {'color': 'red', 'bold': True, 'inverse': True}
        }
        colored_formatter = CustomColoredFormatter(fmt=FORMAT_CONSOLE, field_styles=field_styles, level_styles=level_styles)
        return colored_formatter
    else:
        return None


class CustomColoredFormatter(coloredlogs.ColoredFormatter):
    # Override method in order to colorize the log level instead of the message
    def format(self, record):
        style = self.nn.get(self.level_styles, record.levelname)
        if style and coloredlogs.Empty is not None:
            copy = coloredlogs.Empty()
            copy.__class__ = record.__class__
            copy.__dict__.update(record.__dict__)
            copy.levelname = ansi_wrap(coerce_string(record.levelname), **style)
            record = copy
        # Delegate the remaining formatting to the base formatter.
        return logging.Formatter.format(self, record)
