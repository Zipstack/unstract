"""Lightweight Celery app for dispatching tasks to worker-v2 workers.

The Django backend uses Redis as its Celery broker for internal tasks
(beat, periodic tasks, etc.). The worker-v2 workers (executor,
file_processing, etc.) use RabbitMQ as their broker.

This module provides a Celery app connected to RabbitMQ specifically
for dispatching tasks (via ExecutionDispatcher) to worker-v2 workers.

Problem: Celery reads the ``CELERY_BROKER_URL`` environment variable
with highest priority — overriding constructor args, ``conf.update()``,
and ``config_from_object()``.  Since Django sets that env var to Redis,
every Celery app created in this process inherits Redis as broker.

Solution: Subclass Celery and override ``connection_for_write`` /
``connection_for_read`` so they always use our explicit RabbitMQ URL,
bypassing the config resolution chain entirely.
"""

import logging
import os
from urllib.parse import quote_plus

from celery import Celery
from django.conf import settings
from kombu import Queue

logger = logging.getLogger(__name__)

_worker_app: Celery | None = None


class _WorkerDispatchCelery(Celery):
    """Celery subclass that forces an explicit broker URL.

    Works around Celery's env-var-takes-priority behaviour where
    ``CELERY_BROKER_URL`` always overrides per-app configuration.
    The connection methods are the actual points where Celery opens
    AMQP/Redis connections, so overriding them is both sufficient
    and safe.
    """

    _explicit_broker: str | None = None

    def connection_for_write(self, url=None, *args, **kwargs):
        return super().connection_for_write(
            url=url or self._explicit_broker, *args, **kwargs
        )

    def connection_for_read(self, url=None, *args, **kwargs):
        return super().connection_for_read(
            url=url or self._explicit_broker, *args, **kwargs
        )


def get_worker_celery_app() -> Celery:
    """Get or create a Celery app for dispatching to worker-v2 workers.

    The app uses:
    - RabbitMQ as broker (WORKER_CELERY_BROKER_URL env var)
    - Same PostgreSQL result backend as the Django Celery app

    Returns:
        Celery app configured for worker-v2 dispatch.

    Raises:
        ValueError: If WORKER_CELERY_BROKER_URL is not set.
    """
    global _worker_app
    if _worker_app is not None:
        return _worker_app

    broker_url = os.environ.get("WORKER_CELERY_BROKER_URL")
    if not broker_url:
        raise ValueError(
            "WORKER_CELERY_BROKER_URL is not set. "
            "This should point to the RabbitMQ broker used by worker-v2 "
            "workers (e.g., amqp://admin:password@rabbitmq:5672//)."
        )

    # Reuse the same PostgreSQL result backend as Django's Celery app
    result_backend = (
        f"db+postgresql://{settings.DB_USER}:"
        f"{quote_plus(settings.DB_PASSWORD)}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/"
        f"{settings.CELERY_BACKEND_DB_NAME}"
    )

    app = _WorkerDispatchCelery(
        "worker-dispatch",
        set_as_current=False,
        fixups=[],
    )
    # Store the explicit broker URL for use in connection overrides
    app._explicit_broker = broker_url

    app.conf.update(
        result_backend=result_backend,
        task_queues=[Queue("executor")],
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        result_extended=True,
    )

    _worker_app = app
    # Log broker host only (mask credentials)
    safe_broker = broker_url.split("@")[-1] if "@" in broker_url else broker_url
    logger.info(
        "Created worker dispatch Celery app (broker=%s)", safe_broker
    )
    return _worker_app
