import os
from urllib.parse import quote_plus

from django.conf import settings
from kombu import Queue


def is_rabbitmq_ha_enabled() -> bool:
    """Check if RabbitMQ HA mode with quorum queues is enabled."""
    return os.environ.get("RABBITMQ_HA_ENABLED", "").lower() == "true"


def make_queue(name: str) -> Queue:
    """Create a kombu Queue with x-queue-type: quorum.

    Always declares the queue as quorum type.  Callers are responsible
    for only invoking this helper when HA mode is enabled (i.e. inside
    an ``if is_rabbitmq_ha_enabled():`` guard).

    This is necessary because Celery/kombu sends x-queue-type: classic
    by default, overriding the server-side default_queue_type setting.

    Internal Celery queues (pidbox, reply queues) are not affected
    since they are managed by Celery internals and not listed here.

    Args:
        name: Queue name.

    Returns:
        kombu Queue instance with quorum queue arguments.
    """
    kwargs: dict = {"name": name, "queue_arguments": {"x-queue-type": "quorum"}}
    return Queue(**kwargs)


class CeleryConfig:
    """Specifies celery configuration

    Refer https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """

    # Result backend configuration
    result_backend = (
        f"db+postgresql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.CELERY_BACKEND_DB_NAME}"
    )

    # Broker URL configuration
    broker_url = settings.CELERY_BROKER_URL

    # Task serialization and content settings
    accept_content = ["json"]
    task_serializer = "json"
    result_serializer = "json"
    result_extended = True

    # Timezone and logger settings
    timezone = "UTC"
    worker_hijack_root_logger = False

    beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"

    task_acks_late = True


# When HA is enabled, declare all backend-managed queues as quorum type
# and override QoS semantics for quorum queue compatibility.
# This block runs at import time (same pattern as LLM Whisperer's celeryconfig.py).
if is_rabbitmq_ha_enabled():
    # All queues consumed by the main backend Celery app
    # (worker, worker-logging, worker-metrics)
    _BACKEND_QUEUES = [
        "celery",
        "celery_api_deployments",
        "celery_periodic_logs",
        "celery_log_task_queue",
        "dashboard_metric_events",
    ]
    CeleryConfig.task_queues = [make_queue(q) for q in _BACKEND_QUEUES]

    # Quorum queues do not support global (channel-level) QoS.
    # Celery detects RabbitMQ >= 3.3 and sends basic.qos with global=True,
    # which quorum queues reject with NOT_IMPLEMENTED.
    # Override to per-consumer prefetch.
    from kombu.transport import pyamqp

    pyamqp.Transport.qos_semantics_matches_spec = lambda self, conn: True
