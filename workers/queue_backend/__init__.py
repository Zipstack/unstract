"""Queue-backend seam for workers.

This module is the single place where the choice of queue substrate
(Celery+RabbitMQ today; PG Queue in the future) lives.

Today both entry points are no-op aliases over Celery primitives:

* ``dispatch(task_name, args, kwargs, queue)`` -> ``current_app.send_task(...)``
* ``@worker_task`` -> ``@shared_task``

A later phase will route specific tasks through a non-Celery substrate
(PG Queue) based on configuration; until then everything goes to Celery.
The exact routing mechanism is intentionally not pinned here.

Call sites should migrate to this module so the eventual substrate switch
is a single-flag operation rather than a codebase-wide rewrite.
"""

from .decorator import worker_task
from .dispatch import dispatch

__all__ = ["dispatch", "worker_task"]
