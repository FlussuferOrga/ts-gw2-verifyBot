import socket
import json
import threading

class Server(object):
    '''
    Server for broadcasting messages.
    '''
    def __init__(self, port, max_clients = 5, timeout = 10):
        self.socket = socket.socket()
        self.port = port
        self.max_clients = max_clients
        self.timeout = timeout
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # make sure we don't have to wait for a socket timeout if the server crashes
        self.lock = threading.Lock()

    def send(self, cladr, message):
        '''
        Sends a message to a client.

        cladr: tuple (client,addr) as stored in self.clients.
        message: the message. Can be any object.
        returns: either the original cladr or None, the latter signifying that the client could not be reached (timeout)
        '''
        client,addr = cladr
        try:
            x = client.send(json.dumps(message).encode("utf-8"))
            print(x)
        except BrokenPipeError:
            print("Broken pipe for client %s:%s. Cleaning up connection." % (addr[0],str(addr[1])))
            return None
        except Exception as ex:
            print("Unexpected error while trying to broadcast to client %s:%s: %s" % (addr[0],str(addr[1]),str(ex)))
        return cladr

    def broadcast(self, message):
        '''
        Sends a message to all clients.
        Broadcasting a message will filter out all clients that have timed out in the meanwhile.

        message: the message. Can be any object.
        '''
        self.lock.acquire()      
        self.clients = list(filter(lambda c: c is not None, [self.send(c, message) for c in self.clients]))
        self.lock.release() 

    def run(self):
        self.socket.bind(("", self.port))
        self.socket.listen(self.max_clients)
        self.socket.settimeout(self.timeout)
        self.clients = []

        while True:
            try:
                cladr = self.socket.accept()
                self.clients.append(cladr)
            except socket.timeout:
                pass  

class Client(object):
    ''' just for testing '''
    import socket

    def __init__(self, server_address):
        s = socket.socket()

        host = socket.socket()
        port = 10137

        s.connect((server_address, port))
        mes = s.recv(1024)
        print(json.loads(mes.decode("utf-8")))
