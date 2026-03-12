"""RabbitMQ HA (quorum queue) configuration for Celery apps.

Centralises the quorum-queue and QoS fixup so that every WorkerBuilder
variant applies the same logic.
"""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from celery import Celery

    from ...models.worker_models import WorkerCeleryConfig


def apply_rabbitmq_ha(app: "Celery", worker_celery_config: "WorkerCeleryConfig") -> None:
    """Declare quorum queues and patch QoS when RabbitMQ HA is enabled.

    Must be called *after* all config overrides have been merged into
    ``app.conf`` so that HA declarations always take precedence.

    Does nothing when the ``RABBITMQ_HA_ENABLED`` env var is not ``true``.
    """
    if os.environ.get("RABBITMQ_HA_ENABLED", "").lower() != "true":
        return

    from kombu import Queue
    from kombu.transport import pyamqp

    quorum_args = {"x-queue-type": "quorum"}
    app.conf.task_queues = [
        Queue(q, queue_arguments=quorum_args)
        for q in sorted(worker_celery_config.queue_config.all_queues())
    ]

    # Quorum queues don't support global (channel-level) QoS.  Celery
    # detects RabbitMQ >= 3.3 and sends basic.qos with global=True,
    # which quorum queues reject with NOT_IMPLEMENTED.
    pyamqp.Transport.qos_semantics_matches_spec = lambda self, conn: True
