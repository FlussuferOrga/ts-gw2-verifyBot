import socket
import json
import threading
import schedule
import types
from TS3Auth import log
from abc import ABC, abstractmethod
from deprecation import deprecated
import selectors
from twisted.internet import task
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ServerFactory
from twisted.internet.endpoints import TCP4ServerEndpoint

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

class NonBlockingServer(TCPServer):
    @deprecated(details="Use TwistedServer instead")
    def __init__(self, port, ts_connection, max_clients = 5, timeout = 10, terminator_symbol = "\n", client_message_handler = lambda c,m: False, local_only = True):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = port
        self.ts_connection = ts_connection.copy()
        self.max_clients = max_clients
        self.timeout = timeout
        self.terminator_symbol = terminator_symbol
        self.client_message_handler = client_message_handler
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # make sure we don't have to wait for a socket timeout if the server crashes
        self.socket.setblocking(False)
        self.lock = threading.Lock()
        self.local_only = local_only
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.socket, selectors.EVENT_READ, data=None)

    def send(self, sock, message, lock = True):
        if lock:
            self.lock.acquire()
        print("sending %s" % (json.dumps(message).encode("utf-8"),))
        try:
            sock.settimeout(self.timeout) # FIXME
            sock.sendall(json.dumps(message).encode("utf-8"))
        except BrokenPipeError as e:
            self.closeClient(sock)
        except socket.timeout:
            pass
        if lock:
            self.lock.release()

    def broadcast(self, message):
        with self.lock:
            for sock in [v.fileobj for k,v in self.selector.get_map().items()]: # must create utility list in case the underlying list changes during iteration (client closes)
                self.send(sock, message, lock = False)

    def run(self):
        self.socket.bind(("127.0.0.1" if self.local_only else "", self.port))
        self.socket.listen(self.max_clients)
        while True:
            events = self.selector.select(timeout=None)
            for key, mask in events:
                if key.data is None:
                    self.acceptClient(key.fileobj)
                else:
                    self.handleMessage(key, mask)

    def closeClient(self, clientsocket):
        with self.lock:
            self.selector.unregister(clientsocket)
            clientsocket.close()

    def acceptClient(self, clientsocket, n = 1024):
        with self.lock:
            conn, addr = clientsocket.accept()  # Should be ready to read
            conn.setblocking(False)
            data = types.SimpleNamespace(addr=addr, inb=b'', outb=b'')
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
            self.selector.register(conn, events, data=data)

    def handleMessage(self, key, mask, n = 1024):
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            recv_data = None
            try:
                recv_data = sock.recv(n)  # Should be ready to read
            except ConnectionResetError:
                pass # this effectivly is the same as reading nothing, which results in closing the connection
            if recv_data:
                try:
                    self.client_message_handler(self, sock, json.loads(recv_data))
                except json.decoder.JSONDecodeError:
                    # HTTP "Bad Request" code
                    self.send(sock, "400".encode("utf-8"))
            else:
                self.closeClient(sock)

class ThreadedServer(TCPServer):
    @deprecated(details="Use TwistedServer instead")
    def __init__(self, port, ts_connection, max_clients = 5, timeout = 10, terminator_symbol = "\n", client_message_handler = lambda c,m: False, local_only = True):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #socket.socket()
        self.port = port
        self.ts_connection = ts_connection.copy()
        self.max_clients = max_clients
        self.timeout = timeout
        self.terminator_symbol = terminator_symbol
        self.client_message_handler = client_message_handler
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # make sure we don't have to wait for a socket timeout if the server crashes
        self.socket.setblocking(False)
        self.broadcast_lock = threading.Lock()
        self.handle_message_lock = threading.Lock()
        self.clients = []
        self.local_only = local_only
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.socket, selectors.EVENT_READ, data=None)

    def send(self, cladr, message):
        ''' cladr: tuple (client,addr,thread) as stored in self.clients. '''
        client,addr,thread = cladr
        try:
            client.send(json.dumps(message).encode("utf-8"))
        except BrokenPipeError:
            log("Broken pipe for client %s:%s. Cleaning up connection." % (addr[0],str(addr[1])))
            return None
        except Exception as ex:
            log("Unexpected error while trying to broadcast to client %s:%s: %s" % (addr[0],str(addr[1]),str(ex)))
        return cladr

    def broadcast(self, message):
        self.broadcast_lock.acquire()
        closed = []
        opened = []
        # python's list.append does not return the modified list, so there is no elegant functional way to do this
        for c in self.clients:
            r = self.send(c,message)
            if r is not None:
                opened.append(c)
            else:
                closed.append(c)
        for cl,addr,t in closed:
            cl.close()
        self.clients = opened
        #self.clients = list(filter(lambda c: c is not None, [self.send(c, message) for c in self.clients]))
        self.broadcast_lock.release() 

    def run(self):
        self.socket.bind(("127.0.0.1" if self.local_only else "", self.port))
        self.socket.listen(self.max_clients)
        self.socket.settimeout(self.timeout)
        self.clients = []
        while True:
            try:
                c,addr = self.socket.accept()
                t = threading.Thread(target=self.acceptClient, args=(c,)).start()
                self.clients.append((c,addr,t))
            except socket.timeout:
                pass  
    
    def acceptClient(self, clientsocket, n = 1024):
        closed = False
        data = "";
        while not closed:
            try:
                packet = clientsocket.recv(n);
                if packet:
                    data += packet.decode("utf-8")
                if (packet and len(packet) < n) or self.terminator_symbol in data:
                    pkts = data.split(self.terminator_symbol)
                    mes  = pkts[0]
                    data = self.terminator_symbol.join(pkts[1:])
                    try:
                        self.client_message_handler(self, clientsocket, json.loads(mes))
                    except json.decoder.JSONDecodeError:
                        # HTTP "Bad Request" code
                        clientsocket.send("400".encode("utf-8"))
            except OSError as e:
                closed = e.errno == 9 # bad file descriptor -> connection was closed -> stop thread


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