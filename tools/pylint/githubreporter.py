import sys

from pylint.reporters.text import TextReporter


class GithubReporter(TextReporter):
    """Report messages and layouts."""

    SEVERITY_MAPPING = {
        "I": "info",
        "C": "info",
        "R": "info",
        "W": "warning",
        "E": "error",
        "F": "error",
    }

    def __init__(self, output=sys.stdout):
        self.severity_mapping = dict(GithubReporter.SEVERITY_MAPPING)
        TextReporter.__init__(self, output)

    def write_message(self, msg):
        severity = self.severity_mapping.get(msg.C, None)
        output = msg.format(self._template)
        if severity is not None:
            output = severity + ":" + output
        self.writeln(output)


def register(linter):
    """Register the reporter classes with the linter."""
    linter.register_reporter(GithubReporter)
