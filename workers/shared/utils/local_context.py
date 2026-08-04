"""Worker-specific local context without Django dependencies.
This provides the StateStore functionality needed by workers.
"""

import os
import threading
from enum import StrEnum
from typing import Any


class ConcurrencyMode(StrEnum):
    """Concurrency mode for :class:`StateStore`.

    ``StrEnum`` (not a bare ``Enum``) is load-bearing for TWO reasons, both of which
    produced a hard ``RuntimeError: Unknown concurrency mode`` at runtime (UN-3893):

    1. **A set env var used to break it.** ``mode`` is read as
       ``os.environ.get("CONCURRENCY_MODE", ConcurrencyMode.THREAD)``, so setting the
       variable yields a plain ``str``. Against a bare ``Enum``, ``"thread" ==
       ConcurrencyMode.THREAD`` is **False** — so even the CORRECT value took the
       whole backend down. ``StrEnum`` members ARE strings, so this now compares equal.
    2. **Duplicate module identity.** This module exists in three places
       (``backend/utils``, ``workers/shared/utils``, ``workers/shared/infrastructure``)
       and can be imported under more than one path in a merged tree, producing two
       distinct ``ConcurrencyMode`` CLASSES. Members of different Enum classes never
       compare equal; ``StrEnum`` members compare by string value, so identity of the
       defining class no longer matters.

    Keep this a ``StrEnum``. Reverting it to ``Enum`` re-opens both failures, and both
    are invisible until runtime.
    """

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
