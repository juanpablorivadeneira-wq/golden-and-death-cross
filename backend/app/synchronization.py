from functools import wraps
from threading import RLock

_lock = RLock()

def serialized(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapper
