from .abstract_controller import AbstractController


class HealthController(AbstractController):
    def _routes(self):
        @self.api.route("/health", methods=["GET"])
        def _health():
            return "OK"
