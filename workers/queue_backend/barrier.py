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
from typing import TYPE_CHECKING, Any, Protocol

from celery import chord

from .fairness import FairnessKey
from .handle import BarrierHandle

if TYPE_CHECKING:
    from celery.canvas import Signature

logger = logging.getLogger(__name__)


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
    call is byte-identical to the inline ``chord(...)`` it replaces.
    The only additional behaviour is the optional ``fairness`` header
    attachment, which is an additive wire-level change (consumers that
    don't read the header are unaffected — same backward-compat
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
    ) -> BarrierHandle | None:
        """See :class:`Barrier.enqueue`."""
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
