"""API Deployment Worker

Lightweight Celery worker for handling API deployment workflows.
Uses internal APIs instead of direct Django ORM access.

This worker handles:
- API deployment workflow executions
- File batch processing for API deployments
- Status tracking and error handling
- API-specific execution logic
"""

from .tasks import async_execute_bin_api
from .worker import app as celery_app

__all__ = ["celery_app", "async_execute_bin_api"]

__version__ = "1.0.0"
