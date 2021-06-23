from threading import Thread
from typing import Any, Callable, Optional


class ClosableLoopingThread(Thread):

    def __init__(self, name: Optional[str] = ..., work: Optional[Callable[..., Any]] = ...) -> None:
        super().__init__(group=None, target=self.loop, name=name, daemon=True)

        self._closed = False
        self._work = work

    def is_closed(self):
        return self._closed

    def close(self):
        self._closed = True

    def loop(self) -> None:
        while not self._closed:
            self._work()
