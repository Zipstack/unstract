"""Distributed barrier — abstraction over the chord-completion pattern.

The two production chord call sites (``shared/workflow/execution/
orchestration_utils.py`` and ``api-deployment/tasks.py``) need to wait
for a fan-out of header tasks to all complete, then fire a callback
with the aggregated results. Today that's implemented by Celery's
``chord(header)(body)`` primitive, which is the highest-risk Celery
construct at our scale — silent task drops at ~130K-task scale are
documented in the PG Queue decision journey.

This module provides the ``Barrier`` protocol and a ``CeleryChordBarrier``
implementation that wraps the existing ``chord(...)`` call 1:1. Lifting
both call sites to ``Barrier`` gives Phase 6b a place to land an
alternative implementation (e.g. ``RedisDecrBarrier`` using the labs
``DECR remaining:{exec_id}`` pattern, or — later in Phase 8 — a
``PgBarrier`` using SKIP LOCKED) without touching the call sites a
second time.

**Phase 6a (this PR): wrapper only — behaviour-preserving uplift.**
``CeleryChordBarrier.enqueue(...)`` produces byte-identical wire output
to the direct ``chord(...)`` calls it replaces *when ``fairness=None``*.
When a ``FairnessKey`` is passed (which both production call sites
now do), each header task and the callback additionally carry an
``x-fairness-key`` AMQP header. That's an additive wire-level change —
consumers ignore unknown headers — same posture as Phase 5.1's
``dispatch()`` plumbing. Mixed-version rolling deploys are safe in
both directions: old workers ignore the new header; new workers
handle messages without the header identically to today.

Phase 6b (separate PR) will add ``RedisDecrBarrier`` as a second
implementation, gated by ``WORKER_BARRIER_BACKEND`` env flag (default
``chord``). Phase 6c is the rollout.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, NotRequired, Protocol, TypedDict

from celery import chord

from unstract.core.data_models import DEFAULT_WORKFLOW_TRANSPORT

from .fairness import FairnessKey
from .handle import BarrierHandle

if TYPE_CHECKING:
    from celery.canvas import Signature

logger = logging.getLogger(__name__)

# Shared barrier-key TTL — both the Redis and PG backends bound an orphaned
# barrier (header tasks that never complete) by the same env var, since only one
# backend is active per deployment. One definition here prevents drift.
_DEFAULT_BARRIER_TTL_SECONDS = 6 * 60 * 60  # 6h


def barrier_ttl_seconds() -> int:
    """Barrier TTL from ``WORKER_BARRIER_KEY_TTL_SECONDS`` (default 6h).

    Read at call time so tests can flip it. Invalid / non-positive values raise,
    matching ``get_barrier()``'s loud-on-misconfig posture — a TTL shorter than
    execution wall-clock would tear barriers down early (spurious behaviour).
    """
    raw = os.getenv("WORKER_BARRIER_KEY_TTL_SECONDS")
    if raw is None:
        return _DEFAULT_BARRIER_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"WORKER_BARRIER_KEY_TTL_SECONDS={raw!r} is not an integer. Unset it "
            f"to default to {_DEFAULT_BARRIER_TTL_SECONDS}s (6h)."
        ) from exc
    if value <= 0:
        raise ValueError(
            f"WORKER_BARRIER_KEY_TTL_SECONDS={value} must be a positive integer. "
            f"Unset it to default to {_DEFAULT_BARRIER_TTL_SECONDS}s (6h)."
        )
    return value


# PG barrier stuck-timeout — the "no progress" deadline for a PG-backed barrier.
# Unlike the Redis backend's fixed key TTL, the PG barrier's ``expires_at`` SLIDES:
# it's re-stamped to ``now() + this`` on enqueue AND on every decrement, so a
# barrier only "expires" (→ the reaper marks it ERROR) after this long with NO
# batch completing. Default 2.5h matches Celery's per-task ``FILE_PROCESSING_TASK_
# TIME_LIMIT`` (9000s), giving crash / runaway parity: a batch whose worker died
# (or that runs longer than Celery would allow) stalls progress and is reaped at
# ~this bound, PROMPTLY (not at the old ~6h barrier expiry). A per-PROGRESS window
# is invariant to how many batches run in parallel (``MAX_PARALLEL_FILE_BATCHES``
# is dynamic per-org), so — unlike a per-execution age cap — it never false-fails a
# legitimately long multi-batch run: any completion refreshes the deadline.
_DEFAULT_BARRIER_STUCK_TIMEOUT_SECONDS = 9000  # 2.5h, = Celery FILE_PROCESSING hard limit


def barrier_stuck_timeout_seconds() -> int:
    """PG barrier stuck-timeout from ``WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS`` (default 2.5h).

    Read at call time (tests flip it). Invalid / non-positive values raise,
    matching :func:`barrier_ttl_seconds`'s loud-on-misconfig posture — this bounds
    how long a stalled execution stays non-terminal, so a garbled value must fail
    fast rather than silently disable the recovery net.
    """
    raw = os.getenv("WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS")
    if raw is None:
        return _DEFAULT_BARRIER_STUCK_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS={raw!r} is not an integer. Unset "
            f"it to default to {_DEFAULT_BARRIER_STUCK_TIMEOUT_SECONDS}s (2.5h)."
        ) from exc
    if value <= 0:
        raise ValueError(
            f"WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS={value} must be a positive "
            f"integer. Unset it to default to "
            f"{_DEFAULT_BARRIER_STUCK_TIMEOUT_SECONDS}s (2.5h)."
        )
    return value


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
    # 9e: the WorkflowTransport the aggregating callback is fired on when the
    # barrier completes. Absent / ``None`` → legacy Celery dispatch
    # (``current_app.apply_async`` — the ``.link`` path). ``"pg_queue"`` → the
    # fire-and-forget PG path self-chains the callback via dispatch onto PG.
    # Named ``transport`` (a WorkflowTransport value, e.g. ``"pg_queue"``) — NOT
    # ``backend``, to avoid confusion with ``QueueBackend`` (``"pg"``).
    transport: NotRequired[str | None]


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
        transport: str = DEFAULT_WORKFLOW_TRANSPORT,
    ) -> BarrierHandle | None:
        """Enqueue ``header_tasks`` and a single callback to fire on completion.

        ``transport`` is the per-execution transport (9e). Only ``PgBarrier``
        acts on it (``pg_queue`` → fire-and-forget PG fan-out instead of Celery
        ``.link``); the Celery/Redis substrates accept it for Protocol parity
        and ignore it (they are only ever reached on the ``celery`` transport).

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

        ``app_instance`` is a Celery app today (the Protocol leaks
        this concrete dependency for the same reason the
        ``CeleryChordBarrier`` does — Phase 6b's RedisDecrBarrier will
        narrow this to a smaller Protocol). The argument is the
        ``app`` from the producer's task context and must expose
        ``.signature(name, kwargs=..., queue=..., headers=...)``.
        """
        ...


class CeleryChordBarrier:
    """Thin wrapper around ``celery.chord``.

    Behaviour-preserving: the ``chord(header_tasks)(callback_signature)``
    call shape is the same as the inline ``chord(...)`` it replaces.
    Wire output is byte-identical to the pre-Barrier path when
    ``fairness=None``; when a ``FairnessKey`` is passed the only
    addition is the ``x-fairness-key`` AMQP header on each header
    task and the callback (additive wire-level change — consumers
    that don't read the header are unaffected, same backward-compat
    posture as Phase 5.1's ``dispatch()`` fairness plumbing).

    Future ``RedisDecrBarrier`` and ``PgBarrier`` implementations will
    live alongside this class and be selected by the
    ``WORKER_BARRIER_BACKEND`` env flag (Phase 6b).
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
        transport: str = DEFAULT_WORKFLOW_TRANSPORT,
    ) -> BarrierHandle | None:
        """See :class:`Barrier.enqueue`."""
        del transport  # Celery chord is only reached on the celery transport.
        # Empty-header guard goes FIRST so a zero-task run skips
        # signature construction / fairness serialisation entirely.
        # Any failure in those paths is now constrained to the
        # non-empty branch where the work is actually needed.
        if not header_tasks:
            execution_id = callback_kwargs.get("execution_id")
            pipeline_id = callback_kwargs.get("pipeline_id")
            logger.info(
                f"[exec:{execution_id}] [pipeline:{pipeline_id}] "
                "Zero header tasks detected — skipping barrier enqueue "
                "(parent should handle pipeline status updates directly)"
            )
            return None

        try:
            # Use ``fairness.as_header()`` — the single wire-shape
            # encoder, also used by ``dispatch.py``. Constructing the
            # header dict inline here would risk silent divergence
            # from the bare-dispatch path.
            fairness_headers = fairness.as_header() if fairness else None

            # Build the callback-signature kwargs explicitly. When
            # ``fairness=None`` the resulting call shape is
            # byte-identical to the pre-Barrier ``app.signature(name,
            # kwargs=..., queue=...)`` (no spurious ``headers=None``).
            signature_kwargs: dict[str, Any] = {
                "kwargs": callback_kwargs,
                "queue": callback_queue,
            }
            if fairness_headers:
                signature_kwargs["headers"] = fairness_headers
            callback_signature = app_instance.signature(
                callback_task_name, **signature_kwargs
            )

            # Stamp fairness onto each header signature via
            # ``Signature.clone().set(headers=...)`` rather than
            # in-place ``.set(...)`` on the caller's list. Cloning
            # avoids cross-tenant header leakage if a future retry
            # path or signature cache ever re-uses the original
            # ``header_tasks`` list with a different ``FairnessKey``.
            if fairness_headers:
                signed_header_tasks = [
                    task.clone().set(headers=fairness_headers) for task in header_tasks
                ]
            else:
                signed_header_tasks = header_tasks

            result = chord(signed_header_tasks)(callback_signature)

            logger.info(
                f"Barrier enqueued via CeleryChordBarrier — "
                f"header_tasks={len(signed_header_tasks)}, "
                f"callback={callback_task_name}, "
                f"queue={callback_queue}"
            )

            return result

        except Exception:
            # ``logger.exception`` auto-attaches the traceback — needed
            # for debugging broker outages / serialisation failures
            # at the chord entry point. Add the readily-available
            # context so a Sentry/log triage gets execution/pipeline/
            # callback/queue identifiers alongside the stack.
            execution_id = callback_kwargs.get("execution_id")
            pipeline_id = callback_kwargs.get("pipeline_id")
            logger.exception(
                f"[exec:{execution_id}] [pipeline:{pipeline_id}] "
                f"Failed to enqueue barrier "
                f"(callback={callback_task_name}, queue={callback_queue}, "
                f"header_tasks={len(header_tasks)})"
            )
            raise
