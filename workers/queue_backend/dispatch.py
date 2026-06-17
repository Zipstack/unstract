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
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from celery import current_app

from .fairness import DEFAULT_PRIORITY, FairnessKey
from .handle import DispatchHandle
from .pg_queue import PgQueueClient, to_payload
from .routing import QueueBackend, select_backend

logger = logging.getLogger(__name__)

# pg_queue_message.queue_name used when a dispatch carries no Celery queue.
_DEFAULT_PG_QUEUE = "default"

# Task names already logged as PG-routed in this process — bounds the cutover
# log to once per task name (per prefork child).
_pg_routing_logged: set[str] = set()

# Per-thread client, reused across dispatches (it self-recovers a dead
# connection). The worker pool is prefork (each child a single thread), so
# this is effectively one client per child; ``threading.local`` keeps it
# correct under a ``-P threads`` pool too, since a libpq connection is not
# safe for concurrent use across threads. (A gevent pool shares one thread
# across greenlets and would need a connection pool — out of scope while
# prefork is the deployment.)
_pg_local = threading.local()


def _get_pg_client() -> PgQueueClient:
    client = getattr(_pg_local, "client", None)
    if client is None:
        client = PgQueueClient()
        _pg_local.client = client
    return client


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
    backend: QueueBackend | None = None,
) -> DispatchHandle:
    """Enqueue a task by name onto its selected transport.

    ``fairness`` is attached as the ``x-fairness-key`` header on the Celery
    path / serialised into the message on the PG path. Pass ``None`` for
    non-workflow worker tasks.

    ``backend`` is a per-call transport override. When ``None`` (the default,
    and every call site today) the transport is the env allow-list decision
    via :func:`select_backend` — behaviour is unchanged. When set, it wins
    over the allow-list: this is the seam the execution-level PG pipeline (9e
    PR 2c) uses to route a whole execution's header/callback dispatches onto
    PG without opting their task *names* into ``WORKER_PG_QUEUE_ENABLED_TASKS``
    (the allow-list is for leaf tasks; the coupled pipeline's migration unit is
    the execution, carried in the payload — see ``routing.py``). The override
    only forces the *transport*; it does not bypass ``_enqueue_pg``'s no-silent-
    fallback contract.
    """
    resolved = backend if backend is not None else select_backend(task_name)
    if resolved is QueueBackend.PG:
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
    pg_queue = queue or _DEFAULT_PG_QUEUE
    if task_name not in _pg_routing_logged:
        # Log the routing *decision* once per task, BEFORE the send — it's
        # true regardless of send outcome, so a first-dispatch failure
        # (DB down / unmigrated) must not suppress the one announcement.
        # INFO so it survives a default log config; once-per-task bounds it.
        _pg_routing_logged.add(task_name)
        logger.info(
            "PG-queue: routing task=%r to Postgres (queue=%r). Requires the "
            "PG consumer to be running, or it will not execute.",
            task_name,
            pg_queue,
        )
    payload = to_payload(
        task_name, args=args, kwargs=kwargs, queue=queue, fairness=fairness
    )
    try:
        # Carry org_id + L3 priority onto the row so the dequeue can order by
        # priority. A bare dispatch (fairness=None) writes the neutral defaults
        # (org_id None → "" / DEFAULT_PRIORITY).
        msg_id = _get_pg_client().send(
            pg_queue,
            payload,
            org_id=fairness.org_id if fairness is not None else None,
            priority=(
                fairness.pipeline_priority if fairness is not None else DEFAULT_PRIORITY
            ),
        )
    except Exception:
        # Re-raise with a breadcrumb (raw psycopg2.Error / a json.dumps
        # TypeError on a non-serialisable arg would otherwise propagate with
        # no "this was a PG-routed dispatch" context). No Celery fallback.
        logger.exception(
            "PG-queue: failed to enqueue task=%r to queue=%r", task_name, pg_queue
        )
        raise
    return PgDispatchHandle(id=str(msg_id))
