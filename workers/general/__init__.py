"""General Worker

Lightweight Celery worker for general tasks including webhook notifications
and general workflow executions. Uses internal APIs instead of direct Django ORM access.

This worker handles:
- Webhook notification delivery
- General workflow executions (non-API deployments)
- Background task processing
- Notification delivery status tracking
"""

from .tasks import async_execute_bin_general, send_webhook_notification
from .worker import app as celery_app

__all__ = ["celery_app", "send_webhook_notification", "async_execute_bin_general"]

__version__ = "1.0.0"
