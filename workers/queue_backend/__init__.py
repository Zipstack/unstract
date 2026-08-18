"""Queue-backend seam.

Single place where the substrate choice (Celery today; PG Queue later)
lives. Both entry points are transparent passthroughs to Celery today.

The ``Barrier`` substrate is runtime-selectable via the
``WORKER_BARRIER_BACKEND`` env var:

- ``chord`` (default) — ``CeleryChordBarrier``, the thin wrapper around
  ``celery.chord(header)(body)``. Byte-identical wire to the
  pre-abstraction code path; current production behaviour.
- ``redis`` — ``RedisDecrBarrier``, the labs-design distributed-counter
  pattern (``DECR remaining:{exec_id}`` + per-task ``RPUSH``-based
  result aggregation). Replaces only the chord aggregation primitive;
  dispatch / retries / monitoring still ride on Celery.

**Default-safety posture.** The env defaults to ``chord``, so a merge
into ``main`` is zero-impact: a downstream env (``unstract-cloud``,
self-hosted, etc.) that does not set ``WORKER_BARRIER_BACKEND`` runs
the same substrate it ran yesterday. The new ``RedisDecrBarrier`` code
is dormant until an operator explicitly flips the flag.

Unknown values raise — operators get a loud error at module import
time rather than silently falling back, which would mask a typo'd
flag in a production env.

**Queue-transport routing (separate axis).** ``dispatch()`` consults
:func:`~queue_backend.routing.select_backend`, which reads the
PG-queue routing table (``WORKER_PG_QUEUE_ENABLED_TASKS``) to decide
Celery-vs-PG per task. This is orthogonal to the barrier choice above:
the barrier is *how a batch's fan-in fires the callback*; the transport
is *how messages travel*. Both default to Celery. The routing table is
a scaffold today — PG-selected tasks still ride Celery (no PG consumer
yet) — so it is observable but inert.
"""

import os
from enum import StrEnum

from .barrier import Barrier, BarrierHandle, CeleryChordBarrier
from .decorator import worker_task
from .dispatch import dispatch
from .fairness import FairnessKey
from .pg_barrier import (
    PgBarrier,
    barrier_pg_abort,
    barrier_pg_decr_and_check,
)
from .redis_barrier import (
    RedisDecrBarrier,
    barrier_abort,
    barrier_decr_and_check,
)
from .routing import QueueBackend, select_backend

__all__ = [
    "Barrier",
    "BarrierBackend",
    "BarrierHandle",
    "CeleryChordBarrier",
    "FairnessKey",
    "PgBarrier",
    "QueueBackend",
    "RedisDecrBarrier",
    "barrier_abort",
    "barrier_decr_and_check",
    "barrier_pg_abort",
    "barrier_pg_decr_and_check",
    "dispatch",
    "get_barrier",
    "select_backend",
    "worker_task",
]


class BarrierBackend(StrEnum):
    """Enumeration of ``Barrier`` substrate choices.

    Used as the canonical reference for the ``WORKER_BARRIER_BACKEND``
    env value, the factory's dispatch table, and tests that flip the
    env. Subclassing ``StrEnum`` (Python 3.11+) means ``BarrierBackend.CHORD
    == "chord"`` at runtime, so the enum members can stand in anywhere
    a string is expected — including ``os.environ`` reads.
    """

    CHORD = "chord"
    REDIS = "redis"
    PG = "pg"


def get_barrier() -> Barrier:
    """Return the ``Barrier`` implementation selected by env.

    Reads ``WORKER_BARRIER_BACKEND`` at call time so test harnesses
    that ``monkeypatch.setenv`` can flip the substrate per-test
    without a module reload. Production call sites construct the
    barrier once per process (module-level singleton in
    ``orchestration_utils.py``) so the env read happens at worker
    startup — flag flips require pod restart, same posture as every
    other ``WORKER_*`` env in the codebase.

    Default ``BarrierBackend.CHORD`` mirrors the current production
    substrate. An unknown value raises ``ValueError`` so a typo'd
    ``redis`` → ``rediz`` doesn't silently fall back to chord (which
    would invalidate the canary).
    """
    raw = os.getenv("WORKER_BARRIER_BACKEND", BarrierBackend.CHORD.value)
    try:
        backend = BarrierBackend(raw.strip().lower())
    except ValueError:
        valid = tuple(b.value for b in BarrierBackend)
        raise ValueError(
            f"WORKER_BARRIER_BACKEND={raw!r} is not a recognised "
            f"barrier backend. Valid values: {valid}. Unset the env var "
            f"to default to {BarrierBackend.CHORD.value!r}."
        ) from None

    if backend is BarrierBackend.CHORD:
        return CeleryChordBarrier()
    if backend is BarrierBackend.REDIS:
        return RedisDecrBarrier()
    if backend is BarrierBackend.PG:
        return PgBarrier()
    # Unreachable — StrEnum constructor would have raised above for
    # anything not in the enum. Defensive raise so the type checker
    # sees an exhaustive match.
    raise AssertionError(f"Unhandled BarrierBackend: {backend!r}")
