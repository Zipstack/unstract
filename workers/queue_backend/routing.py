"""Queue-transport routing gate (Strangler-Fig).

Decides whether a given dispatch should ride the **Celery** transport
(today's only real path) or the future **PG Queue** (PGMQ) transport,
based on a per-task-type opt-in allow-list read from env:

- ``WORKER_PG_QUEUE_ENABLED_TASKS`` — comma-separated task names routed
  to PG. Empty / unset → everything routes to Celery.

**Why an allow-list, not a global boolean.** A single
``WORKER_QUEUE_BACKEND=pg`` switch would move *all* traffic at once —
the big-bang migration the PG Queue rollout explicitly forbids. The
allow-list lets an operator migrate one task type at a time
(drain-and-cutover) and roll back instantly by removing an entry.

(Per-org granularity is intentionally out of scope here. When tenant-level
canarying is needed it slots in behind :func:`select_backend` as a small
additive change — no call site touches the routing decision directly.)

**Scaffold posture.** This module only makes the routing *decision*.
In the current phase there is no PG consumer, so ``dispatch()`` still
sends PG-selected tasks via Celery (the decision is observable in logs
but inert). ``select_backend()`` is the seam where the real PG dispatch
lands in a later phase.

**Fail-safe parsing.** Unlike ``get_barrier()`` (which raises on an
unrecognised value, because a typo'd substrate must not silently fall
back), the routing table is a membership set with no "invalid value"
concept: blanks and stray whitespace are simply dropped. Malformed or
empty config can only ever resolve to the safe ``CELERY`` default —
``select_backend()`` never raises.
"""

from __future__ import annotations

import os
from enum import StrEnum

# Env var name kept as a module literal (mirrors how the sibling
# ``WORKER_BARRIER_BACKEND`` flag is read in ``queue_backend.__init__``)
# so the queue-backend seam stays self-contained.
_ENABLED_TASKS_ENV_VAR = "WORKER_PG_QUEUE_ENABLED_TASKS"


class QueueBackend(StrEnum):
    """Transport a dispatch is routed to.

    ``StrEnum`` (3.11+) so ``QueueBackend.CELERY == "celery"`` holds at
    runtime — members stand in anywhere a string is expected.
    """

    CELERY = "celery"
    PG = "pg"


def _parse_allow_list(env_var: str) -> frozenset[str]:
    """Parse a comma-separated env allow-list into a set.

    Trims surrounding whitespace per entry and drops blanks, so
    ``"a, b ,, c"`` → ``{"a", "b", "c"}`` and ``""`` / unset → ``frozenset()``.
    Read at call time (not import) so test harnesses that
    ``monkeypatch.setenv`` flip the table per-test without a reload.
    """
    raw = os.getenv(env_var, "")
    return frozenset(entry.strip() for entry in raw.split(",") if entry.strip())


def select_backend(task_name: str) -> QueueBackend:
    """Return the transport a dispatch should ride.

    ``PG`` if ``task_name`` is in ``WORKER_PG_QUEUE_ENABLED_TASKS``;
    otherwise ``CELERY``. Empty / unset allow-list → always ``CELERY``.

    Never raises — the worst case is the safe ``CELERY`` default.
    """
    if task_name in _parse_allow_list(_ENABLED_TASKS_ENV_VAR):
        return QueueBackend.PG
    return QueueBackend.CELERY
