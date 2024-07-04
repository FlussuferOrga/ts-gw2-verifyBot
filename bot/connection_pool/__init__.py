"""
Idea & Base from https://pypi.org/project/connection-pool/ https://github.com/zhouyl/ConnectionPool
Modification by https://github.com/Xyaren
"""
import logging
import queue
import threading
from typing import Callable, ContextManager, Generic, TypeVar

import time

LOG = logging.getLogger(__name__)


class ConnectionInitializationException(Exception):
    """When it was not possible to instantiate a new connection, throw this exception"""


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


_T = TypeVar("_T")


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

    def __str__(self):
        return f"WrapperConnection[{self.connection}]"


class ConnectionPool(Generic[_T]):
    """Connection pool class, can be used for pymysql/memcache/redis/... 等

    It can be called as follows：
        pool = ConnectionPool(create=redis.Redis)

    You can also specify the create call by lambda：
        pool = ConnectionPool(create=lambda: redis.Redis(host="127.0.0.1"))

    Or through functools.partial
        from functools import partial
        pool = ConnectionPool(create=partial(redis.Redis, host="127.0.0.1"))
    """

    __wrappers = {}

    def __init__(self,
                 create: Callable[[], _T],
                 destroy_function: Callable[[_T], None] = None,
                 checkout_function: Callable[[_T], None] = None,
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
        if not hasattr(create, "__call__"):
            raise ValueError('"create" argument is not callable')

        self._create = create
        self._destroy_function = destroy_function
        self._checkout_function = checkout_function
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
                 redis.set("foo","bar)
         """
        self._lock.acquire()

        try:
            while self._max_size and self._pool.empty() and self._size >= self._max_size:
                if not self._block:
                    raise TooManyConnections("Too many connections")

                self._lock.wait()  # Wait for idle connection

            try:
                wrapped = self._pool.get_nowait()  # Get one from the free connection pool

                # test connection before handing it out
                try:
                    self._test(wrapped)
                except Expired as ex:  # connection was not healthy
                    LOG.info("Connection %s was expired on checkout", wrapped, exc_info=ex)
                    self._destroy(wrapped, f"Expired on checkout: {ex}")
                    return self.item()  # recursion: now that the bad connection is removed from the pool start over.
            except queue.Empty:  # no connection in pool
                wrapped = None

            if wrapped is None:
                try:
                    wrapped = self._wrapper(self._create())  # Create new connection
                    LOG.debug("Connection %s created", wrapped)
                    self._size += 1
                except Exception as ex:
                    raise ConnectionInitializationException("A new connection for the pool could not be created.") from ex
            else:
                LOG.debug("Connection %s will be checked out from the pool", wrapped)
        finally:
            self._lock.release()

        if self._checkout_function:
            self._checkout_function(wrapped.connection)
        return wrapped.using()

    def release(self, conn):
        """Release a connection, let the connection return to the connection pool

         When the connection usage exceeds the limit / exceeds the limit time, the connection will be destroyed
        """
        self._lock.acquire()
        wrapped = self._wrapper(conn)

        try:
            self._test(wrapped)
        except Expired as ex:
            self._destroy(wrapped, f"Expired on release: {ex}")
        else:
            LOG.debug("Connection %s will be released into the pool", wrapped)
            self._pool.put_nowait(wrapped)
            self._lock.notify_all()  # Notify other threads that there are idle connections available
        finally:
            self._lock.release()

    def _destroy(self, wrapped, reason):
        """Destroy a connection"""
        LOG.debug("Connection %s will be destroyed. Reason: %s", wrapped, reason)

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
            raise UsageExceeded(f"Usage exceeds {self._max_usage:d} times")

        if self._ttl and (wrapped.created + self._ttl) < time.time():
            raise TtlExceeded(f"TTL exceeds {self._ttl:d} secs")

        if self._idle and (wrapped.last + self._idle) < time.time():
            raise IdleExceeded(f"Idle exceeds {self._idle:d} secs")

        if self._test_function:
            try:
                is_healthy = self._test_function(wrapped.connection)
            except Exception as ex:
                raise Unhealthy("Connection test determined that the connection is not healthy by exception") from ex
            if not is_healthy:
                raise Unhealthy("Connection test determined that the connection is not healthy")

    def close(self):
        self._lock.acquire()
        try:
            q = self._pool
            for _ in range(0, self._size):
                try:
                    self._destroy(q.get(timeout=10), "Pool closing")
                except queue.Empty:
                    pass
        finally:
            self._lock.release()
