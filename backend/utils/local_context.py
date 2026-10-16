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
    # Keys holding a value cached from another key, keyed by that source key.
    # Setting or clearing the source drops them, so a cached value never
    # outlives the request or task that set the value it was built from,
    # whichever code path sets it.
    _derived_keys: dict[str, set[str]] = {}

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
    def register_derived_key(cls, source_key: str, derived_key: str) -> None:
        """Drop ``derived_key`` whenever ``source_key`` is set or cleared."""
        cls._derived_keys.setdefault(source_key, set()).add(derived_key)

    @classmethod
    def _drop_derived(cls, key: str) -> None:
        for derived_key in cls._derived_keys.get(key, ()):
            if hasattr(cls.thread_local, derived_key):
                delattr(cls.thread_local, derived_key)

    @classmethod
    def get(cls, key: str) -> Any:
        if cls.mode == ConcurrencyMode.THREAD:
            return cls._get_thread_local(key)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)

    @classmethod
    def set(cls, key: str, val: Any) -> None:
        if cls.mode == ConcurrencyMode.THREAD:
            cls._drop_derived(key)
            return cls._set_thread_local(key, val)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)

    @classmethod
    def clear(cls, key: str) -> None:
        if cls.mode == ConcurrencyMode.THREAD:
            # Before the delete, which raises when the key was never set.
            cls._drop_derived(key)
            return cls._del_thread_local(key)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)
