"""Shared task-handle protocol.

Single ``TaskHandle`` contract every ``queue_backend`` entry point
returns: ``dispatch()`` (bare task) and ``Barrier.enqueue()`` (chord /
future DECR / future PG-SKIP-LOCKED). Celery's ``AsyncResult``
satisfies this via ``.id``; future non-Celery substrate handles must
expose the same attribute so call sites that log ``chord_id`` /
``task_id`` keep working.

Originally split as separate ``DispatchHandle`` and ``BarrierHandle``
Protocols — they were byte-for-byte identical, which Vishnu's review
on PR #2024 correctly flagged as a drift risk. Consolidated into
``TaskHandle`` here; both old names are kept as documentation aliases
for now.
"""

from __future__ import annotations

from typing import Protocol


class TaskHandle(Protocol):
    """Return-value contract for any ``queue_backend`` enqueue path.

    Celery's ``AsyncResult`` satisfies this via ``.id``. A future
    non-Celery substrate handle must expose the same attribute so
    call sites that log ``chord_id`` / ``task_id`` keep working.
    """

    id: str


# Documentation aliases. Kept so existing imports and docstring
# references don't break, but they all refer to the same single
# Protocol — no more drift risk.
DispatchHandle = TaskHandle
BarrierHandle = TaskHandle
