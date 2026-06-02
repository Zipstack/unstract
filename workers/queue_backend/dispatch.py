"""Transport-agnostic task dispatch.

Thin pass-through to ``celery.current_app.send_task``; the indirection
is the seam — a future per-task router can land here without touching
call sites.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from celery import current_app

from .fairness import FAIRNESS_HEADER_NAME, FairnessKey


class DispatchHandle(Protocol):
    """Minimum contract every dispatch substrate must satisfy.

    Celery's ``AsyncResult`` satisfies this via ``.id``; any future
    substrate handle must expose the same attribute.
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
    """Enqueue a task by name.

    ``fairness`` is attached as the ``x-fairness-key`` header (not in
    kwargs). Pass ``None`` for non-workflow worker tasks.
    """
    headers = {FAIRNESS_HEADER_NAME: fairness.to_dict()} if fairness is not None else None
    return current_app.send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        headers=headers,
    )
