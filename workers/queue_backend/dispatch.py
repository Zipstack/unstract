"""Transport-agnostic task dispatch.

Routes each task to its transport via :func:`select_backend`:

- **Celery** (default) — a thin pass-through to ``current_app.send_task``.
- **PG Queue** — when a task is opted into ``WORKER_PG_QUEUE_ENABLED_TASKS``,
  the task is serialised and enqueued to ``pg_queue_message`` (9b); the PG
  consumer (9c) drains and runs it.

The default (empty allow-list) routes everything to Celery, so dispatch is
unchanged unless an operator explicitly opts a task in.

.. warning::
   A task opted into the PG queue **requires the PG consumer to be running**
   — otherwise the message is durably enqueued but never executed. Only opt
   in tasks once the consumer is deployed (and, per the migration-coherence
   decision, only *leaf* tasks until execution-level routing exists).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from celery import current_app

from .fairness import FairnessKey
from .handle import DispatchHandle
from .pg_queue import PgQueueClient, to_payload
from .routing import QueueBackend, select_backend

logger = logging.getLogger(__name__)

# pg_queue_message.queue_name used when a dispatch carries no Celery queue.
_DEFAULT_PG_QUEUE = "default"

# Task names already logged as PG-routed in this process — bounds the cutover
# log to once per task name (per prefork child).
_pg_routing_logged: set[str] = set()

# Process-level client, reused across dispatches (it self-recovers a dead
# connection). One per prefork child.
_pg_client: PgQueueClient | None = None


def _get_pg_client() -> PgQueueClient:
    global _pg_client
    if _pg_client is None:
        _pg_client = PgQueueClient()
    return _pg_client


@dataclass(frozen=True, slots=True)
class PgDispatchHandle:
    """:class:`~queue_backend.handle.TaskHandle` for a PG-enqueued task.

    ``id`` is the ``pg_queue_message.msg_id`` (as a string), so call sites
    that read ``handle.id`` keep working across the Celery/PG boundary.
    """

    id: str


def dispatch(
    task_name: str,
    *,
    args: Sequence[Any] | None = None,
    kwargs: Mapping[str, Any] | None = None,
    queue: str | None = None,
    fairness: FairnessKey | None = None,
) -> DispatchHandle:
    """Enqueue a task by name onto its selected transport.

    ``fairness`` is attached as the ``x-fairness-key`` header on the Celery
    path / serialised into the message on the PG path. Pass ``None`` for
    non-workflow worker tasks.
    """
    if select_backend(task_name) is QueueBackend.PG:
        return _enqueue_pg(task_name, args, kwargs, queue, fairness)

    headers = fairness.as_header() if fairness is not None else None
    return current_app.send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        headers=headers,
    )


def _enqueue_pg(
    task_name: str,
    args: Sequence[Any] | None,
    kwargs: Mapping[str, Any] | None,
    queue: str | None,
    fairness: FairnessKey | None,
) -> PgDispatchHandle:
    """Serialise + enqueue a PG-routed task to ``pg_queue_message``.

    A PG enqueue failure raises (no silent Celery fallback — that would
    hide the failure or risk double-dispatch).
    """
    payload = to_payload(
        task_name, args=args, kwargs=kwargs, queue=queue, fairness=fairness
    )
    msg_id = _get_pg_client().send(
        queue or _DEFAULT_PG_QUEUE,
        payload,
        org_id=fairness.org_id if fairness is not None else None,
    )
    if task_name not in _pg_routing_logged:
        # INFO + once-per-task: visible under a default log config, bounded.
        _pg_routing_logged.add(task_name)
        logger.info(
            "PG-queue: task=%r enqueued to Postgres (queue=%r, msg_id=%s). "
            "Requires the PG consumer to be running, or it will not execute.",
            task_name,
            queue or _DEFAULT_PG_QUEUE,
            msg_id,
        )
    return PgDispatchHandle(id=str(msg_id))
