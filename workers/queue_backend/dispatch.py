"""Transport-agnostic task dispatch.

Thin pass-through to ``celery.current_app.send_task`` today. The
indirection is the seam — a future per-task router can be added here
without touching call sites.

The signature intentionally exposes only what the current call sites
actually use (args, kwargs, queue, fairness). More Celery options can
be added when a real call site needs them — not before.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from celery import current_app

from .fairness import FAIRNESS_HEADER_NAME, FairnessKey


class DispatchHandle(Protocol):
    """The minimum contract every dispatch substrate must satisfy.

    Celery's ``AsyncResult`` satisfies this today via ``.id``. Any
    future substrate handle must expose the same attribute so existing
    callers — e.g. ``scheduler/tasks.py`` — keep working unchanged.
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

    Args:
        task_name: Registered task name (e.g. "send_webhook_notification").
        args: Positional task args. Forwarded verbatim; Celery normalises
            ``None`` internally.
        kwargs: Keyword task args. Forwarded verbatim; Celery normalises
            ``None`` internally.
        queue: Target queue name. Defaults to the task's bound queue.
        fairness: Multi-tenant routing metadata (org_id, priority, tier).
            When provided, attached to the Celery message as the
            ``x-fairness-key`` header — out-of-band of the task body's
            kwargs, so a task whose signature doesn't accept
            ``**kwargs`` is unaffected. Consumers reach it via
            ``self.request.headers`` on bound tasks.

    Returns:
        A handle to the enqueued task. ``.id`` is guaranteed; everything
        else is substrate-specific and callers must not rely on it.
    """
    headers = {FAIRNESS_HEADER_NAME: fairness.to_dict()} if fairness is not None else None
    return current_app.send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        headers=headers,
    )
