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
        code.append(f"\n# Thread: {id2name[threadId]}({threadId:d})")
        for filename, lineno, name, line in traceback.extract_stack(stack):
            code.append(f'File: "{filename}", line {lineno:d}, in {name}')
            if line:
                code.append(f" {line.strip()}")
    join = "\n".join(code)
    return join
