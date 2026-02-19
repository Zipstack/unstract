"""Executor Worker

Celery worker for running extraction executors.
Dispatches ExecutionContext to registered executors and returns
ExecutionResult via the Celery result backend.
"""

from .worker import app as celery_app

__all__ = [
    "celery_app",
]
