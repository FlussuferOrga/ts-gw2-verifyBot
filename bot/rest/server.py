import logging
import threading
from typing import Optional, Union

import waitress  # productive serve
from flask import Flask
from waitress.server import BaseWSGIServer, MultiSocketServer

LOG = logging.getLogger(__name__)


class HTTPServer(Flask):
    _server: Optional[Union[MultiSocketServer, BaseWSGIServer]]

    def __init__(self, bot, port):
        super().__init__(__name__,
                         static_url_path='',
                         static_folder="dist/static",
                         template_folder="dist/templates")
        self.bot = bot
        self.port = port
        self._thread = self._create_thread()
        self._server = None

    def start(self):
        LOG.debug("Starting HTTP Server...")
        self._thread.setDaemon(True)
        self._thread.start()

    def _create_thread(self):
        def serve(app, **kw):
            _quiet = kw.pop("_quiet", False)  # test shim
            _profile = kw.pop("_profile", False)  # test shim
            if not _quiet:  # pragma: no cover
                # idempotent if logging has already been set up
                logging.basicConfig()
            self._server = waitress.create_server(app, **kw)
            if not _quiet:  # pragma: no cover
                self._server.print_listen("Serving on http://{}:{}")
            if _profile:  # pragma: no cover
                waitress.profile("self._server.run()", globals(), locals(), (), False)
            else:
                self._server.run()

        thread = threading.Thread(target=serve, kwargs={"app": self, "port": self.port})
        thread.daemon = True
        return thread

    def stop(self):
        LOG.debug("Stopping HTTP Server...")
        if self._server is not None:
            self._server.close()
            LOG.debug("Waiting for HTTP Server Thread to terminate...")
            self._thread.join()
