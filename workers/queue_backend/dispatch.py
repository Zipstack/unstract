"""Transport-agnostic task dispatch.

Today: thin pass-through to ``celery.current_app.send_task``.
Future: per-task routing between Celery and PG Queue based on
``WORKER_PG_QUEUE_ENABLED_TASKS``.

The signature intentionally exposes only what the current two raw
``current_app.send_task`` sites actually use (args, kwargs, queue).
More Celery options can be added when a real call site needs them —
not before.
"""

from __future__ import annotations

from typing import Any

from celery import current_app


def dispatch(
    task_name: str,
    *,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    queue: str | None = None,
) -> Any:
    """Enqueue a task by name.

    Args:
        task_name: Registered task name (e.g. "send_webhook_notification").
        args: Positional task args. Defaults to ``[]``.
        kwargs: Keyword task args. Defaults to ``{}``.
        queue: Target queue name. Defaults to the task's bound queue.

    Returns:
        Whatever the underlying transport returns (today: a Celery
        ``AsyncResult``). Callers should not assume a particular type
        beyond truthiness — this is the seam point that lets PG Queue
        return a different handle later.
    """
    return current_app.send_task(
        task_name,
        args=args if args is not None else [],
        kwargs=kwargs if kwargs is not None else {},
        queue=queue,
    )
