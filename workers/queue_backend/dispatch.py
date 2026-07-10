"""Transport-agnostic task dispatch.

Thin pass-through to ``celery.current_app.send_task``; the indirection
is the seam — a future per-task router can land here without touching
call sites.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from celery import current_app

from .fairness import FairnessKey
from .handle import DispatchHandle


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
    """
    headers = fairness.as_header() if fairness is not None else None
    return current_app.send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        headers=headers,
    )
