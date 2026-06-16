"""PG Queue transport substrate — scaffold.

Reserved home for the PostgreSQL-backed queue substrate (a bespoke
``SKIP LOCKED`` queue, no extension) that will run alongside Celery during
the Strangler-Fig migration. PG Queue is a *core* worker transport — the
intended primary backend — so it lives inside the queue-backend seam next
to its sibling
substrates (``dispatch``, ``routing``, ``barrier``, ``redis_barrier``),
**not** under ``workers/plugins/``, whose plugin *implementation
subdirectories* are the git-ignored overlay copied in at build time (the
directory itself — ``__init__.py``, ``plugin_manager.py`` — is tracked).

A subpackage (rather than a single module like the barriers) because the
real implementation will likely span several modules (config, consumer
poll loop, orchestrator) — exact layout TBD.

9a added the storage + dequeue primitive (:class:`PgQueueClient` over the
``pg_queue_message`` table; the ``SKIP LOCKED`` dequeue lives in the
client). 9b wires :func:`queue_backend.dispatch.dispatch` to enqueue
PG-selected tasks here as a :class:`TaskPayload` instead of sending to
Celery. The consumer poll loop that drains + runs them is 9c — until it
lands, an opted-in task is durably enqueued but not executed.

Default-empty ``WORKER_PG_QUEUE_ENABLED_TASKS`` → everything still routes
to Celery, so this is inert unless a task is explicitly opted in.

Design reference: the PG Queue implementation guide in the labs repo
(``workflow-execution-architecture``). Branch and section pointers move,
so they're tracked on the ticket / PR rather than baked in here.
"""

from .client import PgQueueClient, QueueMessage
from .connection import create_pg_connection
from .leader_election import LeaderLease, default_worker_id, lease_seconds_from_env
from .reaper import (
    LeaderLeaseLike,
    PgReaper,
    TickOutcome,
    reaper_interval_from_env,
    sweep_expired_barriers,
)
from .task_payload import TaskPayload, to_payload

__all__ = [
    "LeaderLease",
    "LeaderLeaseLike",
    "PgQueueClient",
    "PgReaper",
    "QueueMessage",
    "TaskPayload",
    "TickOutcome",
    "create_pg_connection",
    "default_worker_id",
    "lease_seconds_from_env",
    "reaper_interval_from_env",
    "sweep_expired_barriers",
    "to_payload",
]
