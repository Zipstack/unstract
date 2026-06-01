"""Queue-backend seam for workers.

This module is the single place where the choice of queue substrate
(Celery+RabbitMQ today; PG Queue in the future) lives.

Today both entry points are no-op aliases over Celery primitives:

* ``dispatch(task_name, args, kwargs, queue)`` -> ``current_app.send_task(...)``
* ``@worker_task`` -> ``@shared_task``

In a later PR these will gain per-task routing: when a task name appears
in ``WORKER_PG_QUEUE_ENABLED_TASKS``, dispatch routes through the PG Queue
backend instead. Default (env var empty) keeps 100% of traffic on Celery.

Call sites should migrate to this module so the eventual substrate switch
is a single-flag operation rather than a codebase-wide rewrite.
"""

from .decorator import worker_task
from .dispatch import dispatch

__all__ = ["dispatch", "worker_task"]
