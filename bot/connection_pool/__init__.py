"""
Idea & Base from https://pypi.org/project/connection-pool/ https://github.com/zhouyl/ConnectionPool
Modification by https://github.com/Xyaren
"""

import queue
import threading
from typing import Callable, ContextManager, Generic, TypeVar

import time


class TooManyConnections(Exception):
    """When there are too many connections, throw this exception"""


class Expired(Exception):
    """When the connection is not available, throw this exception"""


class UsageExceeded(Expired):
    """The number of uses of the connection exceeds the limit"""


class TtlExceeded(Expired):
    """The connection usage time exceeds the life cycle specified by ttl"""


class IdleExceeded(Expired):
    """Idle time exceeds the time specified by idle"""


class Unhealthy(Expired):
    """Connection was unhealthy"""


_T = TypeVar('_T')


class WrapperConnection(ContextManager[_T]):
    """Used to package database connections in the connection pool to handle life cycle logic"""
    connection: _T

    def __init__(self, pool, connection: _T):
        self.pool = pool
        self.connection = connection
        self.usage = 0
        self.last = self.created = time.time()

    def using(self):
        """Use this method when the connection is called, the number of uses increases by 1"""
        self.usage += 1
        self.last = time.time()
        return self

    def reset(self):
        """Reset connection package status"""
        self.usage = self.last = self.created = 0

    def __enter__(self) -> _T:
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        self.pool.release(self)


class ConnectionPool(Generic[_T]):
    """Connection pool class, can be used for pymysql/memcache/redis/... 等

    It can be called as follows：
        pool = ConnectionPool(create=redis.Redis)

    You can also specify the create call by lambda：
        pool = ConnectionPool(create=lambda: redis.Redis(host='127.0.0.1'))

    Or through functools.partial
        from functools import partial
        pool = ConnectionPool(create=partial(redis.Redis, host='127.0.0.1'))
    """

    __wrappers = {}

    def __init__(self,
                 create: Callable[[], _T],
                 destroy_function: Callable[[_T], None] = None,
                 test_function: Callable[[_T], bool] = None,
                 max_size: int = 10, max_usage: int = 0,
                 ttl: int = 0, idle: int = 60,
                 block: bool = True) -> None:
        """Initialization parameters

            create: must be a callback function
            destroy_function: optional, called on destruction
            test_function: optional, called on returning the connection to the pool to test availability
            max_size: The maximum number of connections. When it is 0, there is no limit. It is not recommended to set it to 0
            max_usage: the number of times the connection can be used, after reaching this number, the connection will be released/closed
            ttl: connection life time, unit (seconds), when the connection reaches the specified time, the connection will be released/closed
            idle: connection idle time, unit (seconds), when the connection is idle for a specified time, it will be released/closed
            block: When the number of connections is full, whether to block waiting for the connection to be released, input False to throw an exception when the connection pool is full
        """
        if not hasattr(create, '__call__'):
            raise ValueError('"create" argument is not callable')

        self._create = create
        self._destroy_function = destroy_function
        self._test_function = test_function
        self._max_size = int(max_size)
        self._max_usage = int(max_usage)
        self._ttl = int(ttl)
        self._idle = int(idle)
        self._block = bool(block)
        self._lock = threading.Condition()
        self._pool = queue.Queue()
        self._size = 0

    def item(self) -> WrapperConnection[_T]:
        """ can be called by with ... as ... syntax

             pool = ConnectionPool(create=redis.Redis)
             with pool.item() as redis:
                 redis.set('foo','bar)
         """
        self._lock.acquire()

        try:
            while (self._max_size and self._pool.empty() and self._size >= self._max_size):
                if not self._block:
                    raise TooManyConnections('Too many connections')

                self._lock.wait()  # Wait for idle connection

            try:
                wrapped = self._pool.get_nowait()  # Get one from the free connection pool
            except queue.Empty:
                wrapped = self._wrapper(self._create())  # Create new connection
                self._size += 1
        finally:
            self._lock.release()

        return wrapped.using()

    def release(self, conn):
        """Release a connection, let the connection return to the connection pool

         When the connection usage exceeds the limit / exceeds the limit time, the connection will be destroyed
        """
        self._lock.acquire()
        wrapped = self._wrapper(conn)

        try:
            self._test(wrapped)
        except Expired:
            self._destroy(wrapped)
        else:
            self._pool.put_nowait(wrapped)
            self._lock.notifyAll()  # Notify other threads that there are idle connections available
        finally:
            self._lock.release()

    def _destroy(self, wrapped):
        """Destroy a connection"""
        if self._destroy_function is not None:
            self._destroy_function(wrapped.connection)

        self._unwrapper(wrapped)
        self._size -= 1

    def _wrapper(self, conn: _T) -> WrapperConnection[_T]:
        if isinstance(conn, WrapperConnection):
            return conn

        _id = id(conn)

        if _id not in self.__wrappers:
            self.__wrappers[_id] = WrapperConnection(self, conn)

        return self.__wrappers[_id]

    def _unwrapper(self, wrapped):
        """Unwrap the connection"""
        if not isinstance(wrapped, WrapperConnection):
            return

        _id = id(wrapped.connection)
        wrapped.reset()
        del wrapped

        if _id in self.__wrappers:
            del self.__wrappers[_id]

    def _test(self, wrapped):
        """Test the availability of the connection, and throw an Expired exception when it is not available"""
        if self._max_usage and wrapped.usage >= self._max_usage:
            raise UsageExceeded('Usage exceeds %d times' % self._max_usage)

        if self._ttl and (wrapped.created + self._ttl) < time.time():
            raise TtlExceeded('TTL exceeds %d secs' % self._ttl)

        if self._idle and (wrapped.last + self._idle) < time.time():
            raise IdleExceeded('Idle exceeds %d secs' % self._idle)

        if self._test_function and not self._test_function(wrapped.connection):
            raise Unhealthy('Connection test determined that the connection is not healthy')
