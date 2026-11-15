"""Single-process source download coordination; never persists job or verdict state."""
from functools import wraps
from threading import Lock, RLock
from weakref import WeakValueDictionary

_guard = Lock()
_locks = WeakValueDictionary()


def single_source(key_of):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            key = key_of(*args, **kwargs)
            with _guard:
                lock = _locks.get(key)
                if lock is None:
                    lock = RLock()
                    _locks[key] = lock
            # The next waiter rechecks the real cache after the first download.
            with lock:
                return function(*args, **kwargs)
        return run
    return decorate
