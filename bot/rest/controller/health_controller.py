from bot.rest import AbstractController


class HealthController(AbstractController):
    def _routes(self):
        @self.api.route("/health", methods=["GET"])
        def _health():
            return "OK"
