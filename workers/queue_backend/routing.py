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

**Observability.** Because the gate is silent-by-construction (a
misrouted task still runs on Celery), the only signals are logs, emitted
at INFO so they survive a default log config: the configured allow-list
is logged once per process (:func:`_log_allow_list_once`, so a typo is
visible even if it never matches a real task), and the first time each
task is routed to PG (``dispatch()``, log-once per task name).

**Fail-safe parsing.** Unlike ``get_barrier()`` (which raises on an
unrecognised value, because a typo'd substrate must not silently fall
back), the routing table is a membership set with no "invalid value"
concept: blanks and stray whitespace are simply dropped. Malformed or
empty config can only ever resolve to the safe ``CELERY`` default —
``select_backend()`` never raises.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum

logger = logging.getLogger(__name__)

# Env var name kept as a module literal (mirrors how the sibling
# ``WORKER_BARRIER_BACKEND`` flag is read in ``queue_backend.__init__``)
# so the queue-backend seam stays self-contained.
_ENABLED_TASKS_ENV_VAR = "WORKER_PG_QUEUE_ENABLED_TASKS"

# One-shot guard so the configured allow-list is logged once per process
# (see ``_log_allow_list_once``). Module-level → per prefork child.
_allow_list_logged = False


class QueueBackend(StrEnum):
    """Transport a dispatch is routed to.

    ``StrEnum`` (3.11+) is inherited for symmetry with ``BarrierBackend``,
    but unlike that enum this one is never read from / written to env —
    only the task-name allow-list is. So callers MUST compare by identity
    (``backend is QueueBackend.PG``), never ``== "pg"``: ``StrEnum`` makes a
    typo'd ``== "cellery"`` a silent ``False`` rather than an error.
    """

    CELERY = "celery"
    PG = "pg"


def _parse_allow_list() -> frozenset[str]:
    """Parse ``WORKER_PG_QUEUE_ENABLED_TASKS`` into a set of task names.

    Trims surrounding whitespace per entry and drops blanks, so
    ``"a, b ,, c"`` → ``{"a", "b", "c"}`` and ``""`` / unset → ``frozenset()``.
    Read at call time (not import) so test harnesses that
    ``monkeypatch.setenv`` flip the table per-test without a reload.
    """
    stripped = (
        entry.strip() for entry in os.getenv(_ENABLED_TASKS_ENV_VAR, "").split(",")
    )
    return frozenset(entry for entry in stripped if entry)


def _log_allow_list_once(allow_list: frozenset[str]) -> None:
    """Log the configured allow-list once per process, at INFO.

    Makes a misconfiguration eyeballable at boot: a typo'd task name
    (``async_execute_bni``) silently routes everything to Celery, but it
    still shows up here so an operator can spot it. Only fires for a
    *non-empty* allow-list — the default (feature off) stays silent so
    the scaffold is truly inert when unused.
    """
    global _allow_list_logged
    if _allow_list_logged or not allow_list:
        return
    _allow_list_logged = True
    logger.info(
        "PG-queue routing enabled for tasks: %s (all others → Celery)",
        sorted(allow_list),
    )


def select_backend(task_name: str) -> QueueBackend:
    """Return the transport a dispatch should ride.

    ``PG`` if ``task_name`` is in ``WORKER_PG_QUEUE_ENABLED_TASKS``;
    otherwise ``CELERY``. Empty / unset allow-list → always ``CELERY``.

    Never raises — the worst case is the safe ``CELERY`` default.
    """
    allow_list = _parse_allow_list()
    _log_allow_list_once(allow_list)
    if task_name in allow_list:
        return QueueBackend.PG
    return QueueBackend.CELERY
