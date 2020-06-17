import threading

import waitress  # productive serve
from flask import Flask, abort, request

import Logger

log = Logger.getLogger()


def try_get(dictionary, key, lower=False, typer=lambda x: x, default=None):
    v = typer(dictionary[key] if key in dictionary else default)
    return v.lower() if lower and isinstance(v, str) else v


class HTTPServer(Flask):
    def __init__(self, bot, host, port):
        super().__init__(__name__)
        self.bot = bot
        self.host = host
        self.port = port

    def start(self):
        # weirdly, specifying the host parameter results in the initial boot message of
        # waitress being posted twice. I am not sure if the routes are also set twice,
        # but other users have reported this behavior as well, so I not taking any chances here.
        # https://stackoverflow.com/a/57074705
        t = threading.Thread(target=waitress.serve, kwargs={"app": self, "port": self.port})
        t.daemon = True
        t.start()

    def stop(self):
        pass  # fixme: stop waitress


def createHTTPServer(bot, host="localhost", port=8080):
    app = HTTPServer(bot, host, port)

    @app.route("/health", methods=["GET"])
    def health():
        return "OK"

    @app.route("/resetroster", methods=["POST"])
    def resetRoster():
        body = request.json
        date = try_get(body, "date", default="dd.mm.yyyy")
        red = try_get(body, "rbl", default=[])
        green = try_get(body, "gbl", default=[])
        blue = try_get(body, "bbl", default=[])
        ebg = try_get(body, "ebg", default=[])
        log.info("Received request to set resetroster. RBL: %s GBL: %s, BBL: %s, EBG: %s" % (", ".join(red), ", ".join(green), ", ".join(blue), ", ".join(ebg)))
        res = app.bot.setResetroster(bot.ts_connection, date, red, green, blue, ebg)
        return "OK" if res == 0 else abort(400, res)

    @app.route("/guild", methods=["POST"])
    def createGuild():
        body = request.json
        name = try_get(body, "name", default=None)
        tag = try_get(body, "tag", default=None)
        groupname = try_get(body, "tsgroup", default=tag)
        contacts = try_get(body, "contacts", default=[])
        log.info("Received request to create guild %s [%s] (Group %s) with contacts %s", name, tag, groupname, ", ".join(contacts))
        res = -1 if name is None or tag is None else app.bot.createGuild(name, tag, groupname, contacts)
        return "OK" if res == 0 else abort(400, res)

    @app.route("/guild", methods=["DELETE"])
    def deleteGuild():
        body = request.json
        name = try_get(body, "name", default=None)
        log.info("Received request to delete guild %s", name)
        res = app.bot.removeGuild(name)
        return "OK" if res == 0 else abort(400, res)

    @app.route("/registration", methods=["DELETE"])
    def deleteRegistration():
        body = request.json
        gw2account = try_get(body, "gw2account", default="")
        log.info("Received request to delete user '%s' from the TS registration database.", gw2account)
        changes = app.bot.removePermissionsByGW2Account(gw2account)
        return {"changes": changes}

    @app.route("/commanders", methods=["GET"])
    def activeCommanders():
        acs = app.bot.getActiveCommanders()
        return acs if acs is not None else abort(503, "")

    return app
