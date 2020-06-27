import sys

import pylint.lint

from tools.pylint.githubreporter import GithubReporter

pylint.lint.Run(args=sys.argv[1:], reporter=GithubReporter())
