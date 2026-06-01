"""Task registration decorator.

Today: a transparent wrapper over ``celery.shared_task``.
Future: registers the task body with whichever substrates are enabled
(Celery + optionally PG Queue), so a single ``@worker_task`` definition
can be served by either consumer.

Accepts both Celery decorator forms — ``shared_task`` handles them
internally, so a pass-through ``*args, **kwargs`` is enough:

    @worker_task
    def healthcheck(self): ...

    @worker_task(bind=True, name="my.task")
    def my_task(self, payload): ...
"""

from __future__ import annotations

from typing import Any

from celery import shared_task


def worker_task(*args: Any, **kwargs: Any) -> Any:
    """Register a function as a worker task via the queue_backend seam.

    Today this is a one-line passthrough to ``celery.shared_task``. The
    indirection is the seam: when a later phase adds PG Queue routing,
    the consumer-registration logic lands here without touching call
    sites.

    The return type is ``Any`` because ``shared_task`` returns different
    objects depending on call form — a ``PromiseProxy`` for the bare
    ``@worker_task`` form and a decorator factory for the parameterised
    ``@worker_task(name=...)`` form. Pinning a tighter type would lock
    out future routing variants without buying real safety today.
    """
    return shared_task(*args, **kwargs)
