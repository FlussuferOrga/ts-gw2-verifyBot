import ctypes
import platform
import threading

LIB = 'libcap.so.2'


# noinspection PyProtectedMember
def enhance_thread_names():
    if platform.system() == "Linux":
        try:
            libcap = ctypes.CDLL(LIB)
        except OSError:
            print('Library {} not found. Unable to set thread name.'.format(LIB))
        else:
            # noinspection PyProtectedMember
            def _name_hack(self):
                # PR_SET_NAME = 15
                libcap.prctl(15, self.name.encode())
                threading.Thread._bootstrap_original(self)

            threading.Thread._bootstrap_original = threading.Thread._bootstrap
            threading.Thread._bootstrap = _name_hack

            # set thread name for main thread
            libcap.prctl(15, threading.current_thread().name.encode())
