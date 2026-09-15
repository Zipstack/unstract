"""Distributed barrier — the fan-out-then-callback seam.

The two production fan-out call sites (``shared/workflow/execution/
orchestration_utils.py`` and ``api-deployment/tasks.py``) need to wait for a
fan-out of header tasks to all complete, then fire a callback with the
aggregated results.

This module holds the ``Barrier`` protocol and the types that cross the
producer → queue → consumer boundary. The single implementation is
:class:`~queue_backend.pg_barrier.PgBarrier`.

**History.** This seam existed to let the substrate be swapped without touching
the call sites twice. It carried three implementations: ``CeleryChordBarrier``
(``celery.chord``, the original), ``RedisDecrBarrier`` (a ``DECR`` counter), and
``PgBarrier``. Selection was runtime, via ``WORKER_BARRIER_BACKEND``. The first
two, the env var, and the ``get_barrier()`` factory were deleted in UN-4078 once
PG became the only transport; the protocol is kept because two call sites still
program against it and it is the natural home for the shared TypedDicts below.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, NotRequired, Protocol, TypedDict

from .fairness import FairnessKey
from .handle import BarrierHandle

if TYPE_CHECKING:
    from celery.canvas import Signature

logger = logging.getLogger(__name__)

# Shared barrier-key TTL — both the Redis and PG backends bound an orphaned
# barrier (header tasks that never complete) by the same env var, since only one
# backend is active per deployment. One definition here prevents drift.
_DEFAULT_BARRIER_TTL_SECONDS = 6 * 60 * 60  # 6h


def _positive_int_env(var: str, default: int, human_default: str) -> int:
    """Read positive-int env ``var``; return *default* when unset, raise (loud) on a
    non-integer or non-positive value. *human_default* is how the default renders in
    the error (e.g. ``"21600s (6h)"``). Shared by the two barrier duration knobs so
    their parse/validate can't drift.
    """
    raw = os.getenv(var)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{var}={raw!r} is not an integer. Unset it to default to {human_default}."
        ) from exc
    if value <= 0:
        raise ValueError(
            f"{var}={value} must be a positive integer. Unset it to default to "
            f"{human_default}."
        )
    return value


def barrier_ttl_seconds() -> int:
    """Barrier TTL from ``WORKER_BARRIER_KEY_TTL_SECONDS`` (default 6h).

    Read at call time so tests can flip it. Invalid / non-positive values raise
    rather than falling back — a TTL shorter than execution wall-clock would tear
    barriers down early (spurious behaviour), so a garbled value must fail loud.
    """
    return _positive_int_env(
        "WORKER_BARRIER_KEY_TTL_SECONDS",
        _DEFAULT_BARRIER_TTL_SECONDS,
        f"{_DEFAULT_BARRIER_TTL_SECONDS}s (6h)",
    )


# PG barrier stuck-timeout — the "no progress" deadline for a PG-backed barrier.
# The barrier's ``last_progress_at`` column (NOT ``expires_at``) is re-stamped to
# bare ``now()`` on enqueue AND on every decrement; the reaper applies THIS timeout
# at query time (``last_progress_at < now() - stuck_timeout``, see
# ``reaper._STRANDED_PREDICATE``), so a barrier is reaped only after this long with
# NO batch completing. The 9000s (2.5h) default sits in the SAME BAND as Celery's
# per-task ``FILE_PROCESSING_TASK_TIME_LIMIT`` — a tunable env shipping 7200 (2h) /
# 10800 (3h) across the sample deployments — giving crash / runaway parity without
# asserting an equality that rots when an operator tunes that var. A per-PROGRESS
# window is invariant to how many batches run in parallel (``MAX_PARALLEL_FILE_
# BATCHES`` is dynamic per-org), so — unlike a per-execution age cap — it never
# false-fails a legitimately long multi-batch run: any completion refreshes it.
_DEFAULT_BARRIER_STUCK_TIMEOUT_SECONDS = 9000  # 2.5h — Celery file-proc band (2h–3h)


def barrier_stuck_timeout_seconds() -> int:
    """PG barrier stuck-timeout from ``WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS`` (default 2.5h).

    Read at call time (tests flip it). Invalid / non-positive values raise,
    matching :func:`barrier_ttl_seconds`'s loud-on-misconfig posture — this bounds
    how long a stalled execution stays non-terminal, so a garbled value must fail
    fast rather than silently disable the recovery net.
    """
    return _positive_int_env(
        "WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS",
        _DEFAULT_BARRIER_STUCK_TIMEOUT_SECONDS,
        f"{_DEFAULT_BARRIER_STUCK_TIMEOUT_SECONDS}s (2.5h)",
    )


class CallbackDescriptor(TypedDict):
    """Serialisable aggregating-callback spec baked into a barrier link signature.

    Crosses a Celery serialisation boundary (producer → broker → worker), so the
    four-key contract is typed to catch a typo/rename before it surfaces as a
    remote ``KeyError`` mid-aggregation. Shared by both the Redis and PG
    backends. ``fairness_headers`` is ``None`` when the producer passed no key.
    """

    task_name: str
    kwargs: dict[str, Any]
    queue: str
    fairness_headers: dict[str, Any] | None
    # Write-only rolling-deploy shim, see LEGACY_TRANSPORT_KEY in
    # unstract.core.data_models. Read by pre-UN-4078 workers only.
    transport: NotRequired[str]


class BarrierContext(TypedDict):
    """Per-batch barrier coordination injected into a PG-dispatched header task.

    The 9e fire-and-forget sibling of :class:`CallbackDescriptor`, and typed for
    the same reason: it crosses producer → PG-queue → consumer, so the contract
    is pinned here to catch a typo/rename at the type layer rather than as a
    remote ``KeyError`` mid-batch. Carried as the ``_barrier_context`` kwarg on
    ``process_file_batch`` so the consumer can claim its slot and run the barrier
    decrement in-body (a PG-consumed task fires no Celery ``.link``).
    """

    execution_id: str
    batch_index: int
    callback_descriptor: CallbackDescriptor


def callback_recovery_identity(
    callback_descriptor: CallbackDescriptor,
) -> tuple[str | None, str | None]:
    """``(execution_id, organization_id)`` from a callback descriptor's kwargs.

    The barrier's recovery net (mark the execution ERROR when a batch strands)
    needs the execution's identity, which the fan-out stamps into the callback's
    ``kwargs`` (they are the aggregating callback's own arguments). Both recovery
    sites — the in-body abort in :mod:`queue_backend.pg_barrier` and the consumer
    poison-drop in :mod:`queue_backend.pg_queue.consumer` — read it through this
    one accessor, so a producer-side kwarg rename is caught here rather than
    silently regressing the safety net in two places. Either field may be ``None``
    (a malformed/legacy descriptor); the callers handle a missing org.
    """
    kwargs = callback_descriptor.get("kwargs") or {}
    return kwargs.get("execution_id"), kwargs.get("organization_id")


class Barrier(Protocol):
    """Fan-out-then-callback primitive.

    Semantically: "enqueue these header tasks in parallel; when all
    complete, fire this callback with the list of header results."
    The concrete substrate (Celery chord today, Redis DECR or PG
    SKIP LOCKED later) is hidden behind this protocol.
    """

    def enqueue(
        self,
        header_tasks: list[Signature],
        *,
        callback_task_name: str,
        callback_kwargs: dict[str, Any],
        callback_queue: str,
        app_instance: Any,
        fairness: FairnessKey | None = None,
    ) -> BarrierHandle | None:
        """Enqueue ``header_tasks`` and a single callback to fire on completion.

        ``None`` is the **sole signal** that no work was enqueued — it
        is returned exclusively when ``header_tasks`` is empty. Any
        substrate-level failure (broker outage, serialisation error,
        etc.) raises rather than returning ``None``, so callers may
        treat ``None`` as "no-op, nothing wrong" and a raised
        exception as a genuine failure. The caller is responsible for
        guarding ``header_tasks`` (e.g. an early-return when files==0)
        if a returned ``None`` is semantically distinct from a normal
        completion in their domain.

        ``fairness``, when provided, is attached as the
        ``x-fairness-key`` header on every enqueued task and the
        callback — same wire shape as ``dispatch()`` uses for bare
        sites. Pass ``None`` for non-workflow-execution callers.

        ``app_instance`` is accepted for backward compatibility with the two
        call sites and is unused by :class:`PgBarrier` — the header tasks are
        dispatched onto the PG queue by name, not through a Celery app.
        """
        ...
