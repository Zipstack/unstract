"""Executor Worker

Celery worker for running extraction executors.
Dispatches ExecutionContext to registered executors and returns
ExecutionResult via the Celery result backend.

``celery_app`` resolves lazily (PEP 562). Importing it eagerly made *every*
consumer of this package pay the executor worker's full bootstrap: ``.worker``
builds the Celery app and imports ``executor.executors``, which pulls in
``LegacyExecutor`` and the whole adapter stack. That is ~9s of work the
file_processing worker never needed — it imports ``ExecutorToolShim`` and some
string constants from this package and dispatches everything else over the PG
queue (UN-4136). Attribute access is unchanged, so ``from executor import celery_app``
still works for callers that genuinely want the app.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from celery import Celery

    celery_app: Celery

__all__ = [
    "celery_app",
]


def __getattr__(name: str) -> object:
    """Resolve ``celery_app`` on first access instead of at import time."""
    if name == "celery_app":
        from .worker import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
