"""Backend-side producer for the PG queue (orchestrator dispatch — 9e PR A / 2d).

The workers own the consumer and the worker-side ``dispatch()`` PG producer; the
backend has the ``pg_queue`` tables but, until now, no way to *enqueue* to them —
it dispatched the orchestrator (``async_execute_bin``) only via Celery. When an
execution rides the ``pg_queue`` transport, the orchestrator itself must run on
PG, so the backend enqueues it here.

Same ``pg_queue_message`` row shape as the workers' ``PgQueueClient.send`` (a
:class:`~unstract.core.data_models.TaskPayload` JSONB), written via the
``PgQueueMessage`` ORM (whose Python-level field defaults supply ``now()`` / ``0``
for the vt/counter columns). The ``TaskPayload`` / ``FairnessPayload`` wire
contract is shared via ``unstract.core`` so producer and consumer agree on the
keys without one codebase importing the other.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pg_queue.models import PgQueueMessage
from unstract.core.data_models import FairnessPayload, TaskPayload

logger = logging.getLogger(__name__)

# Mirror the workers' fairness L3 bounds (``queue_backend.fairness`` — a separate
# codebase, can't be imported). The DB ``CheckConstraint`` on
# ``pg_queue_message.priority`` is the writer-proof backstop; this is the
# friendly pre-check that names the offending value.
_MIN_PRIORITY = 1
_MAX_PRIORITY = 10
DEFAULT_PRIORITY = 5

# Default/general queue name — mirrors the workers' ``QueueName.GENERAL = "celery"``
# (the Celery default queue), used when the caller passes no explicit queue.
DEFAULT_GENERAL_QUEUE = "celery"


def _json_safe(value: Any) -> Any:
    """Round-trip through JSON with ``default=str`` so UUIDs / datetimes in the
    task args/kwargs become strings.

    ``PgQueueMessage.message`` is a plain ``JSONField`` (no Django encoder), and
    the worker consumer already receives string ids on the existing PG dispatch
    path, so coercing here keeps both transports consistent.
    """
    return json.loads(json.dumps(value, default=str))


def enqueue_task(
    *,
    task_name: str,
    queue: str | None,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    org_id: str = "",
    priority: int = DEFAULT_PRIORITY,
    fairness: FairnessPayload | None = None,
) -> int:
    """Enqueue a task onto the PG queue; returns the new ``msg_id``.

    Mirrors ``queue_backend.pg_queue.client.PgQueueClient.send`` so the worker
    consumer can decode and run it. A PG enqueue failure propagates — the caller
    decides; for the orchestrator there is no silent Celery fallback (that would
    hide the failure or risk a double-dispatch).
    """
    if not _MIN_PRIORITY <= priority <= _MAX_PRIORITY:
        raise ValueError(
            f"priority out of range [{_MIN_PRIORITY}, {_MAX_PRIORITY}]: {priority!r}"
        )
    pg_queue = queue or DEFAULT_GENERAL_QUEUE
    message: TaskPayload = {
        "task_name": task_name,
        "args": _json_safe(list(args) if args is not None else []),
        "kwargs": _json_safe(dict(kwargs) if kwargs is not None else {}),
        "queue": pg_queue,
        "fairness": fairness,
    }
    row = PgQueueMessage.objects.create(
        queue_name=pg_queue,
        message=message,
        org_id=org_id or "",
        priority=priority,
    )
    logger.info(
        "PG-queue: enqueued task=%r queue=%r msg_id=%s org=%r",
        task_name,
        pg_queue,
        row.msg_id,
        org_id,
    )
    return row.msg_id
