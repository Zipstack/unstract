"""Backend-side producer for the PG queue (orchestrator dispatch).

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
from unstract.core.data_models import (
    FAIRNESS_DEFAULT_PRIORITY,
    FAIRNESS_MAX_PRIORITY,
    FAIRNESS_MIN_PRIORITY,
    ContinuationSpec,
    FairnessPayload,
    TaskPayload,
)

logger = logging.getLogger(__name__)

# Fairness L3 priority default, re-exported under the producer's name so callers
# (workflow_helper) import one symbol. Bounds + default are the single source of
# truth in unstract.core (shared with the workers' fairness/queue client); the DB
# CheckConstraint on pg_queue_message.priority is the writer-proof backstop.
DEFAULT_PRIORITY = FAIRNESS_DEFAULT_PRIORITY

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
    reply_key: str | None = None,
    on_success: ContinuationSpec | None = None,
    on_error: ContinuationSpec | None = None,
    task_id: str | None = None,
) -> int:
    """Enqueue a task onto the PG queue; returns the new ``msg_id``.

    Mirrors ``queue_backend.pg_queue.client.PgQueueClient.send`` so the worker
    consumer can decode and run it. A PG enqueue failure propagates — the caller
    decides; for the orchestrator there is no silent Celery fallback (that would
    hide the failure or risk a double-dispatch).

    ``reply_key`` marks a **request-reply** dispatch (the executor RPC on PG):
    the executor consumer writes the task's result/error to ``pg_task_result``
    under it for the blocking caller to poll. Omitted = fire-and-forget.

    ``on_success`` / ``on_error`` mark an **async/callback** dispatch
    (``dispatch_with_callback``): the executor consumer self-chains the matching
    continuation after the task runs. ``task_id`` is the dispatch id prepended to
    ``on_error`` as the failed id (Celery ``link_error`` parity). Mutually
    exclusive with ``reply_key`` — passing both is rejected (the consumer checks
    ``reply_key`` first and would silently drop the callback).
    """
    if reply_key is not None and (on_success is not None or on_error is not None):
        raise ValueError(
            "reply_key (request-reply) and on_success/on_error (callback) are "
            "mutually exclusive"
        )
    if not FAIRNESS_MIN_PRIORITY <= priority <= FAIRNESS_MAX_PRIORITY:
        raise ValueError(
            f"priority out of range "
            f"[{FAIRNESS_MIN_PRIORITY}, {FAIRNESS_MAX_PRIORITY}]: {priority!r}"
        )
    pg_queue = queue or DEFAULT_GENERAL_QUEUE
    message: TaskPayload = {
        "task_name": task_name,
        "args": _json_safe(list(args) if args is not None else []),
        "kwargs": _json_safe(dict(kwargs) if kwargs is not None else {}),
        "queue": pg_queue,
        # Coerce like args/kwargs/on_success/on_error: FairnessPayload may carry a
        # UUID/enum/datetime that a plain JSONField insert can't serialise, which
        # would raise at enqueue and drop the task on the PG path only.
        "fairness": _json_safe(fairness) if fairness is not None else fairness,
    }
    # Each optional key is set only when present — keeps fire-and-forget rows
    # byte-identical to before these fields existed.
    if reply_key is not None:
        message["reply_key"] = reply_key
    # Continuation specs carry a nested callback ``kwargs`` dict that may hold a
    # UUID/datetime — coerce like ``args``/``kwargs`` above, else the JSONField
    # insert raises at dispatch time (caller-visible).
    if on_success is not None:
        message["on_success"] = _json_safe(on_success)
    if on_error is not None:
        message["on_error"] = _json_safe(on_error)
    if task_id is not None:
        message["task_id"] = task_id
    # Mirror the worker _enqueue_pg path: log the failure with breadcrumbs before
    # it propagates, so a DB/constraint/serialization error isn't mislabeled by
    # the caller's broad handler.
    try:
        row = PgQueueMessage.objects.create(
            queue_name=pg_queue,
            message=message,
            org_id=org_id or "",
            priority=priority,
        )
    except Exception:
        logger.exception(
            "PG-queue: failed to enqueue task=%r queue=%r org=%r",
            task_name,
            pg_queue,
            org_id,
        )
        raise
    logger.info(
        "PG-queue: enqueued task=%r queue=%r msg_id=%s org=%r",
        task_name,
        pg_queue,
        row.msg_id,
        org_id,
    )
    return row.msg_id
