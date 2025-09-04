"""General Worker

Lightweight Celery worker for general tasks and workflow executions.
Uses internal APIs instead of direct Django ORM access.

This worker handles:
- General workflow executions (non-API deployments)
- Background task processing
- File processing tasks
- Task orchestration and coordination

Note: Webhook notifications are now handled by the dedicated notification worker.
"""

from .tasks import async_execute_bin_general
from .worker import app as celery_app

__all__ = ["celery_app", "async_execute_bin_general"]

__version__ = "1.0.0"
