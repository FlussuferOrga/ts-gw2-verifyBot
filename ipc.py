import socket
import json
import threading
from TS3Auth import log

class Server(object):
    '''
    Server for broadcasting messages.
    '''
    def __init__(self, port, max_clients = 5, timeout = 10, terminator_symbol = "\n", client_message_handler = lambda c,m: False):
        self.socket = socket.socket()
        self.port = port
        self.max_clients = max_clients
        self.timeout = timeout
        self.terminator_symbol = terminator_symbol
        self.client_message_handler = client_message_handler
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # make sure we don't have to wait for a socket timeout if the server crashes
        self.broadcast_lock = threading.Lock()
        self.handle_message_lock = threading.Lock()

    def send(self, cladr, message):
        '''
        Sends a message to a client.

        cladr: tuple (client,addr,thread) as stored in self.clients.
        message: the message. Can be any object.
        returns: either the original cladr or None, the latter signifying that the client could not be reached (timeout)
        '''
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
        '''
        Sends a message to all clients.
        Broadcasting a message will filter out all clients that have timed out in the meanwhile.

        message: the message. Can be any object.
        '''
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
        self.socket.bind(("", self.port))
        self.socket.listen(self.max_clients)
        self.socket.settimeout(self.timeout)
        self.clients = []

        while True:
            try:
                c,addr = self.socket.accept()
                t = threading.Thread(target=self.listenClient, args=(c,)).start()
                self.clients.append((c,addr,t))
            except socket.timeout:
                pass  
    
    def listenClient(self, clientsocket, n = 1024):
        '''
        Listens to incoming messages from a client. 
        Messages from clients must be valid JSON and ended by the terminator symbol.
        (default: \n)
        Listening runs threaded and is stopped automatically for disconnected clients
        as soon as they are detected.
        Fully parsed JSON objects are passed to the client_message_handler function.

        clientsocket: the socket to listen to
        n: buffer size in bytes. Not really relevant, since messages are buffered anyway
        '''
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
                        self.client_message_handler(clientsocket, json.loads(mes))
                    except json.decoder.JSONDecodeError:
                        # HTTP "Bad Request" code
                        clientsocket.send("400".encode("utf-8"))
            except OSError as e:
                closed = e.errno == 9 # bad file descriptor -> connection was closed -> stop thread

import time
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
            "command": "setupresetroster"
        }).encode("utf-8"))
        s.sendall("\n".encode("utf-8"))

        mes = s.recv(1024)

        #print(json.loads(mes.decode("utf-8")))