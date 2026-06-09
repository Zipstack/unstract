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
both call sites to ``Barrier`` gives PG Queue's Phase 8 work somewhere
to land an alternative implementation (e.g. ``RedisDecrBarrier`` using
the labs ``DECR remaining:{exec_id}`` pattern, or a ``PgBarrier`` using
SKIP LOCKED) without touching the call sites a second time.

**Phase 6a (this PR): wrapper only — zero behaviour change.**
``CeleryChordBarrier.enqueue(...)`` produces byte-identical wire output
to the direct ``chord(...)`` calls it replaces. Mixed-version rolling
deploys are safe because both old and new workers run ``chord(...)``
underneath.

Phase 6b (separate PR) will add ``RedisDecrBarrier`` as a second
implementation, gated by ``WORKER_BARRIER_BACKEND`` env flag (default
``chord``). Phase 6c is the rollout.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from celery import chord

from .fairness import FAIRNESS_HEADER_NAME, FairnessKey

logger = logging.getLogger(__name__)


class BarrierHandle(Protocol):
    """Return value contract for a successful ``Barrier.enqueue(...)``.

    Celery's ``AsyncResult`` satisfies this via ``.id``. A future
    non-Celery substrate handle must expose the same attribute so
    call sites that log ``chord_id`` keep working.
    """

    id: str


class Barrier(Protocol):
    """Fan-out-then-callback primitive.

    Semantically: "enqueue these header tasks in parallel; when all
    complete, fire this callback with the list of header results."
    The concrete substrate (Celery chord today, Redis DECR or PG
    SKIP LOCKED later) is hidden behind this protocol.
    """

    def enqueue(
        self,
        header_tasks: list[Any],
        *,
        callback_task_name: str,
        callback_kwargs: dict[str, Any],
        callback_queue: str,
        app_instance: Any,
        fairness: FairnessKey | None = None,
    ) -> BarrierHandle | None:
        """Enqueue ``header_tasks`` and a single callback to fire on completion.

        Returns ``None`` when ``header_tasks`` is empty — matches the
        legacy ``create_chord_execution`` contract that lets parents
        handle pipeline status updates directly for zero-file runs.
        Returns the handle (with ``.id``) otherwise.

        ``fairness``, when provided, is attached as the
        ``x-fairness-key`` header on every enqueued task and the
        callback — same wire shape as ``dispatch()`` uses for bare
        sites. Pass ``None`` for non-workflow-execution callers.
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
        header_tasks: list[Any],
        *,
        callback_task_name: str,
        callback_kwargs: dict[str, Any],
        callback_queue: str,
        app_instance: Any,
        fairness: FairnessKey | None = None,
    ) -> BarrierHandle | None:
        """See :class:`Barrier.enqueue`."""
        try:
            fairness_headers = (
                {FAIRNESS_HEADER_NAME: fairness.to_dict()} if fairness else None
            )

            # Callback signature carries fairness so the chord body
            # consumer (``process_batch_callback`` / ``..._api``) sees
            # the same routing slot the headers carried.
            callback_signature = app_instance.signature(
                callback_task_name,
                kwargs=callback_kwargs,
                queue=callback_queue,
                **({"headers": fairness_headers} if fairness_headers else {}),
            )

            if not header_tasks:
                execution_id = callback_kwargs.get("execution_id")
                pipeline_id = callback_kwargs.get("pipeline_id")
                logger.info(
                    f"[exec:{execution_id}] [pipeline:{pipeline_id}] "
                    "Zero header tasks detected — skipping barrier enqueue "
                    "(parent should handle pipeline status updates directly)"
                )
                return None

            # Stamp fairness onto each pre-built header signature too.
            # The signatures are constructed by the caller (e.g.
            # ``app.signature("process_file_batch", args=[...],
            # queue=...)``); we mutate them in place via
            # ``.set(headers=...)`` because that's celery's documented
            # way to attach message-level headers post-construction.
            if fairness_headers:
                for task in header_tasks:
                    task.set(headers=fairness_headers)

            result = chord(header_tasks)(callback_signature)

            logger.info(
                f"Barrier enqueued via CeleryChordBarrier — "
                f"header_tasks={len(header_tasks)}, "
                f"callback={callback_task_name}, "
                f"queue={callback_queue}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to enqueue barrier: {e}")
            raise
