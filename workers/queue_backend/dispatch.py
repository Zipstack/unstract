"""Transport-agnostic task dispatch.

Thin pass-through to ``celery.current_app.send_task``; the indirection
is the seam — a future per-task router can land here without touching
call sites.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from celery import current_app

from .fairness import FairnessKey
from .handle import DispatchHandle
from .routing import QueueBackend, select_backend

logger = logging.getLogger(__name__)


def dispatch(
    task_name: str,
    *,
    args: Sequence[Any] | None = None,
    kwargs: Mapping[str, Any] | None = None,
    queue: str | None = None,
    fairness: FairnessKey | None = None,
) -> DispatchHandle:
    """Enqueue a task by name.

    ``fairness`` is attached as the ``x-fairness-key`` header (not in
    kwargs). Pass ``None`` for non-workflow worker tasks.

    The transport is chosen by :func:`select_backend` from the PG-queue
    routing table (``WORKER_PG_QUEUE_ENABLED_TASKS``). In this phase the
    table is a scaffold: PG-selected tasks are *logged* but still
    dispatched via Celery, because no PG consumer exists yet. The
    ``QueueBackend.PG`` branch below is the seam where the real PG
    enqueue lands in a later phase — keeping the ``send_task`` call
    outside it guarantees today's wire is byte-identical regardless of
    the routing decision.
    """
    if select_backend(task_name) is QueueBackend.PG:
        logger.debug(
            "PG-queue routing selected for task=%r; dispatching via "
            "Celery (scaffold — no PG consumer yet)",
            task_name,
        )

    headers = fairness.as_header() if fairness is not None else None
    return current_app.send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        headers=headers,
    )
