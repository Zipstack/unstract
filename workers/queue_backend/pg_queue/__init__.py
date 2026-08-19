"""PG Queue transport substrate.

The PostgreSQL-backed queue substrate — a bespoke ``SKIP LOCKED`` queue (no
extension) that runs alongside Celery during the Strangler-Fig migration. PG
Queue is a *core* worker transport — the intended primary backend — so it lives
inside the queue-backend seam next to its sibling substrates (``dispatch``,
``routing``, ``barrier``, ``redis_barrier``), **not** under ``workers/plugins/``,
whose plugin *implementation subdirectories* are the git-ignored overlay copied
in at build time (the directory itself — ``__init__.py``, ``plugin_manager.py``
— is tracked).

A subpackage (rather than a single module like the barriers) because the
implementation spans several modules: the storage + ``SKIP LOCKED`` dequeue
primitive (:class:`PgQueueClient` over the ``pg_queue_message`` table), the
consumer poll loop that drains and runs claimed tasks, the leader-elected
reaper, and the result backend. :func:`queue_backend.dispatch.dispatch` enqueues
a PG-selected task here as a :class:`TaskPayload` instead of sending it to Celery.

Default-empty ``WORKER_PG_QUEUE_ENABLED_TASKS`` → everything still routes to
Celery, so this is inert unless a task is explicitly opted in.
"""

from .client import PgQueueClient, QueueMessage
from .connection import create_pg_connection
from .leader_election import LeaderLease, default_worker_id, lease_seconds_from_env
from .liveness import LivenessServer
from .reaper import (
    LeaderLeaseLike,
    PgReaper,
    ReaperLivenessServer,
    TickOutcome,
    reaper_interval_from_env,
    recover_expired_barriers,
)
from .task_payload import TaskPayload, to_payload

__all__ = [
    "LeaderLease",
    "LeaderLeaseLike",
    "LivenessServer",
    "PgQueueClient",
    "PgReaper",
    "QueueMessage",
    "ReaperLivenessServer",
    "TaskPayload",
    "TickOutcome",
    "create_pg_connection",
    "default_worker_id",
    "lease_seconds_from_env",
    "reaper_interval_from_env",
    "recover_expired_barriers",
    "to_payload",
]
