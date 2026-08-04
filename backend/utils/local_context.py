import os
import threading
from enum import Enum
from typing import Any


class ConcurrencyMode(Enum):
    THREAD = "thread"
    COROUTINE = "coroutine"


class Exceptions:
    UNKNOWN_MODE = "Unknown concurrency mode"


class StateStore:
    mode = os.environ.get("CONCURRENCY_MODE", ConcurrencyMode.THREAD)
    # Thread-safe storage.
    thread_local = threading.local()

    @classmethod
    def _get_thread_local(cls, key: str) -> Any:
        return getattr(cls.thread_local, key, None)

    @classmethod
    def _set_thread_local(cls, key: str, val: Any) -> None:
        setattr(cls.thread_local, key, val)

    @classmethod
    def _del_thread_local(cls, key: str) -> None:
        delattr(cls.thread_local, key)

    @classmethod
    def get(cls, key: str) -> Any:
        if cls.mode == ConcurrencyMode.THREAD:
            return cls._get_thread_local(key)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)

    @classmethod
    def set(cls, key: str, val: Any) -> None:
        if cls.mode == ConcurrencyMode.THREAD:
            return cls._set_thread_local(key, val)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)

    @classmethod
    def clear(cls, key: str) -> None:
        if cls.mode == ConcurrencyMode.THREAD:
            return cls._del_thread_local(key)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)
