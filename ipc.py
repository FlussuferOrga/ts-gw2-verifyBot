import socket
import json
import threading
import schedule
import types
from abc import ABC, abstractmethod
import selectors
from twisted.internet import task
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ServerFactory
from twisted.internet.endpoints import TCP4ServerEndpoint

from flask import Flask, request, Response, abort
import waitress # productive serve
import os # operating system commands -check if files exist

import Logger

log = Logger.getLogger()

def try_get(dictionary, key, lower = False, typer = lambda x: x, default = None):
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
        t = threading.Thread(target = waitress.serve, kwargs = { "app": self, "port": self.port})
        t.daemon = True
        t.start()

    def stop(self):
        pass # fixme: stop waitress



def createHTTPServer(bot, host = "localhost", port = 8080):
    app = HTTPServer(bot, host, port)
    @app.route("/health", methods = ["GET"])
    def health():
        return "OK"

    @app.route("/resetroster", methods = ["POST"])
    def resetRoster():
        body = request.json
        date = try_get(body, "date", default = "dd.mm.yyyy")
        red = try_get(body, "rbl", default = [])
        green = try_get(body, "gbl", default = [])
        blue = try_get(body, "bbl", default = [])
        ebg = try_get(body, "ebg", default = [])
        log.info("Received request to set resetroster. RBL: %s GBL: %s, BBL: %s, EBG: %s" % (", ".join(red), ", ".join(green), ", ".join(blue), ", ".join(ebg)))
        res = app.bot.setResetroster(bot.ts_connection, date, red, green, blue, ebg)
        return Response("OK", "text") if res == 0 else abort(400, res)

    @app.route("/guild", methods = ["POST"])
    def createGuild():
        body = request.json
        name = try_get(body, "name", default = None)
        tag = try_get(body, "tag", default = None)
        groupname = try_get(body, "tsgroup", default = mtag)
        contacts = try_get(body, "contacts", default = [])
        log.info("Received request to create guild %s [%s] (Group %s) with contacts %s", (name, tag, groupname, ", ".join(contacts)))
        res = -1 if name is None or tag is None else app.bot.createGuild(name, tag, groupname, contacts)
        return "OK" if res == 0 else abort(400, res)

    @app.route("/guild", methods = ["DELETE"])
    def deleteGuild():
        body = request.json
        name = try_get(body, "name", default = None)
        log.info("Received request to delete guild %s", name)
        res = app.bot.removeGuild(name)
        return "OK" if res == 0 else abort(400, res)

    @app.route("/registration", methods = ["DELETE"])
    def deleteRegistration():
        body = request.json
        gw2account = try_get(body,"gw2account", default = "")
        log.info("Received request to delete user '%s' from the TS registration database.", gw2account)
        changes = app.bot.removePermissionsByGW2Account(gw2account)
        return {"changes": changes}

    @app.route("/commanders", methods = ["GET"])
    def activeCommanders():
        acs = app.bot.getActiveCommanders()
        return acs if acs is not None else abort(503, "")

    return app


'''
This module enables inter process communication,
meant to have the Discord-bot and the TS3-bot communicate.
Several different approaches have been tried, of which 
all are functioning, but not equally usable.

- ThreadedServer makes the problem that the TS3Connection
  has troubles in a multi thread environment even more obvious.
- NonBlockingServer is okay but very low level, maybe leading to
  bugs I have not yet discovered and don't have the time to test
  thorougly.
- TwistedServer is high-level and therefore probably the most stable.

So at this point, ThreadedServer and NonBlockingServer are deprecated
and will probably be deleted at some point.
'''

class TCPServer(ABC):
    '''
    Server for broadcasting messages.
    '''

    @abstractmethod
    def send(self, socket, message):
        '''
        Sends a message to a client.

        socket: socket, however it is represented in the specific TCPServer
        message: the message. Can be any object.
        returns: either the original socket or None, the latter signifying that the client could not be reached (timeout)
        '''
        pass

    @abstractmethod
    def broadcast(self, message):
        '''
        Sends a message to all clients.
        Broadcasting a message will filter out all clients that have timed out in the meanwhile.

        message: the message. Can be any object.
        '''
        pass

    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def acceptClient(self, clientsocket, n = 1024):
        '''
        Listens to incoming messages from a client. 
        Messages from clients must be valid JSON and ended by the terminator symbol.
        (default: \n)
        Fully parsed JSON objects are passed to the client_message_handler function.

        clientsocket: the socket to listen to
        n: buffer size in bytes. Not really relevant, since messages are buffered anyway
        '''
        pass

class TwistedServer(TCPServer):  
    class BotgartClientConnection(Protocol):
        def __init__(self, factory):
            self.factory = factory

        def connectionMade(self):
            self.factory.clients.append(self)

        def connectionLost(self, reason):
            self.factory.clients.remove(self)

        def dataReceived(self, data):
            try:
                self.factory.server.client_message_handler(self.factory.server, self, json.loads(data.decode("utf-8") ))
            except json.decoder.JSONDecodeError:
                # HTTP "Bad Request" code
                self.factory.server.send(self, "400")

        def send(self, message):
            self.transport.write(json.dumps(message).encode("utf-8"))

        def respond(self, mid, command, response): 
            self.send({
                    "type": "response",
                    "message_id": mid,
                    "command": command,
                    "response": response                    
                })

    class BotgartServerFactory(ServerFactory):
        def __init__(self, server):
            self.clients = []
            self.server = server

        def buildProtocol(self, addr):
            return TwistedServer.BotgartClientConnection(self)

    def __init__(self, port, ts_connection, max_clients = 5, timeout = 10, terminator_symbol = "\n", client_message_handler = lambda c,m: False, local_only = True):
        self.port = port
        self.ts_connection = ts_connection.copy()
        self.terminator_symbol = terminator_symbol
        self.client_message_handler = client_message_handler
        self.local_only = local_only
        self.factory = TwistedServer.BotgartServerFactory(self)     

    def acceptClient(self, clientsocket, n = 1024):
        pass # handled internally

    def run(self):
        endpoint = TCP4ServerEndpoint(reactor, self.port, interface = "127.0.0.1" if self.local_only else "0.0.0.0")
        endpoint.listen(self.factory)
        reactor.run(installSignalHandlers=False) # or else python complains about not running in the main thread

    def send(self, client, message):
        client.send(message)

    def broadcast(self, message):
        for c in self.factory.clients:
            self.send(c, message)

import time
import sys
class Client(object):
    ''' just for testing '''
    import socket
    

    def __init__(self, server_address):
        s = socket.socket()

        host = socket.socket()
        port = 10137

        s.connect((server_address, port))
        s.sendall(json.dumps({
            "type": "post",
            "command": "setupresetroster",
            "args": {"date": "2220.12.19"},
            "longarg": """AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC
DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD
EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG
HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH
IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIii
JJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJJjjj
KKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKKk
LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLlll
MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM
NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNnn
OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO
PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP
QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ
RRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRR
SSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSS
TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT
UUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUUU
VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVvv
WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW
XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"""
        }).encode("utf-8"))
        s.sendall("\n".encode("utf-8"))
        #sys.exit()
        print("sent")
        while True:
            mes = s.recv(1024)
            if mes is None:
                break
            print(mes)

        print(json.loads(mes.decode("utf-8")))