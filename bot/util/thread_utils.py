import threading
import traceback

import sys


def thread_dump() -> str:
    id2name = {}
    for th in threading.enumerate():
        id2name[th.ident] = th.name
    code = []
    # noinspection PyUnresolvedReferences,PyProtectedMember
    frames = sys._current_frames()

    for threadId, stack in frames.items():
        code.append("\n# Thread: %s(%d)" % (id2name[threadId], threadId))
        for filename, lineno, name, line in traceback.extract_stack(stack):
            code.append('File: "%s", line %d, in %s' % (filename, lineno, name))
            if line:
                code.append(" %s" % (line.strip()))
    join = "\n".join(code)
    return join
