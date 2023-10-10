from flask import Response

from .abstract_controller import AbstractController
from ...util import thread_dump


class HealthController(AbstractController):
    def _routes(self):

        @self.api.route("/health", methods=["GET"])
        def _health():
            return Response("OK", 200, None, None, "text/plain")

        @self.api.route("/health/thread-dump", methods=["GET"])
        def _thread_dump():
            return Response(thread_dump(), 200, None, None, "text/plain")
