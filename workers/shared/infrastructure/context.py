"""Worker Context Management - Thread-safe state storage for workers.

This provides StateStore functionality for workers without Django dependencies,
replacing the duplicated 'legacy' version with a proper shared infrastructure module.
"""

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
    """Thread-safe context storage for worker tasks.

    This replaces the Django StateStore functionality for workers,
    enabling context sharing across worker task execution.
    """

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
        try:
            delattr(cls.thread_local, key)
        except AttributeError:
            pass  # Key doesn't exist, ignore

    @classmethod
    def get(cls, key: str) -> Any:
        """Get value from context storage."""
        if cls.mode == ConcurrencyMode.THREAD:
            return cls._get_thread_local(key)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)

    @classmethod
    def set(cls, key: str, val: Any) -> None:
        """Set value in context storage."""
        if cls.mode == ConcurrencyMode.THREAD:
            return cls._set_thread_local(key, val)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)

    @classmethod
    def clear(cls, key: str) -> None:
        """Clear value from context storage."""
        if cls.mode == ConcurrencyMode.THREAD:
            return cls._del_thread_local(key)
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)

    @classmethod
    def clear_all(cls) -> None:
        """Clear ALL values from context storage (critical for preventing data leaks).

        This must be called after each task to prevent data leaking between
        different executions when Celery reuses worker threads.
        """
        if cls.mode == ConcurrencyMode.THREAD:
            # Clear all attributes from thread_local
            for attr in list(vars(cls.thread_local).keys()):
                try:
                    delattr(cls.thread_local, attr)
                except AttributeError:
                    pass  # Already cleared, ignore
        else:
            raise RuntimeError(Exceptions.UNKNOWN_MODE)
