"""Executor-RPC transport routing for the PG path (Phase 9).

The executor "RPC" is a synchronous request-reply: a caller (prompt-studio here)
sends an ``ExecutionContext`` to the executor worker and blocks for the
``ExecutionResult``. The legacy transport is Celery — the SDK
``ExecutionDispatcher`` (``send_task`` + ``AsyncResult.get``). This module adds a
**parallel** Postgres transport that leaves Celery and the SDK completely
untouched (no SDK edit, no change to the ``execute_extraction`` task or the
Celery executor worker):

- :class:`PgExecutionDispatcher` enqueues ``execute_extraction`` onto the PG queue
  with a unique ``reply_key`` and polls ``pg_task_result`` for the reply — same
  ``.dispatch()`` contract as the SDK dispatcher (never raises; failure/timeout →
  ``ExecutionResult.failure``).
- :func:`resolve_executor_transport` is the gate: master
  ``PG_QUEUE_TRANSPORT_ENABLED`` then the **single** Flipt flag
  ``pg_queue_enabled`` — the same flag the execution path uses, so one
  flip turns the whole PG-queue feature on/off (no per-subsystem flags to
  maintain). Fails closed to Celery.
- :class:`RoutingExecutionDispatcher` is what callers get from
  ``PromptStudioHelper._get_dispatcher()``: ``dispatch()`` picks PG-vs-Celery
  **per call** (read at dispatch time → flipping the flag is an instant,
  no-redeploy rollout/rollback); ``dispatch_async`` / ``dispatch_with_callback``
  always delegate to Celery (the callback path is a later slice).

Zero-regression: gate off ⇒ every method delegates to the unchanged Celery
``ExecutionDispatcher`` and no ``pg_task_result`` row is created.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import TYPE_CHECKING, Any

from django.conf import settings

from pg_queue.models import PgTaskResult
from pg_queue.producer import enqueue_task
from unstract.flags.feature_flag import check_feature_flag_status
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.result import ExecutionResult

if TYPE_CHECKING:
    from unstract.sdk1.execution.context import ExecutionContext

logger = logging.getLogger(__name__)

# The SINGLE PG-queue rollout flag — shared with the execution path
# (canonical constant: ``PG_QUEUE_FLAG_KEY`` in workflow_v2/transport.py; the
# string is duplicated here rather than imported to avoid a pg_queue →
# workflow_manager dependency). One flag for the whole feature: on routes the
# executor (and execution) to PG, off keeps Celery — no per-subsystem flags.
PG_QUEUE_FLAG_KEY = "pg_queue_enabled"
_EXECUTE_TASK = "execute_extraction"
# Mirror the SDK's queue-per-executor convention so the PG executor queue name
# matches the Celery one (the queue routes by the row's queue_name column).
_QUEUE_PREFIX = "celery_executor_"
# Caller-side wait default — mirrors the SDK dispatcher (EXECUTOR_RESULT_TIMEOUT
# env, else 3600s) so a PG-routed caller waits exactly as long as a Celery one.
_DEFAULT_TIMEOUT_ENV = "EXECUTOR_RESULT_TIMEOUT"
_DEFAULT_TIMEOUT = 3600
_POLL_INITIAL_SECONDS = 0.2
_POLL_MAX_SECONDS = 2.0


def resolve_executor_transport(context: ExecutionContext) -> bool:
    """True → route this executor dispatch over PG; False → Celery (default).

    Mirrors ``resolve_transport``: master-gated by ``PG_QUEUE_TRANSPORT_ENABLED``,
    then the **single** ``pg_queue_enabled`` Flipt flag (shared across
    the whole PG-queue feature), bucketed per org. **Fails closed to Celery** on a
    closed gate, a blind Flipt, or any error — so the executor never silently
    loses its transport.
    """
    if not settings.PG_QUEUE_TRANSPORT_ENABLED:
        return False
    if os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() != "true":
        logger.warning(
            "resolve_executor_transport: gate ON but FLIPT_SERVICE_AVAILABLE != "
            "true (Flipt blind); using Celery"
        )
        return False
    org = getattr(context, "organization_id", None)
    # %-bucket keyed on org (prompt-studio is org-scoped); fall back to run_id so
    # a context without an org still resolves deterministically.
    entity_id = str(org or getattr(context, "run_id", "") or "default")
    flag_context = {"executor_name": str(context.executor_name)}
    if org:
        flag_context["organization_id"] = str(org)
    try:
        enabled = check_feature_flag_status(
            flag_key=PG_QUEUE_FLAG_KEY, entity_id=entity_id, context=flag_context
        )
    except Exception:
        logger.warning(
            "resolve_executor_transport: Flipt check failed; using Celery",
            exc_info=True,
        )
        return False
    return bool(enabled)


class PgExecutionDispatcher:
    """PG request-reply executor dispatch — drop-in for ``ExecutionDispatcher.dispatch``.

    Enqueues ``execute_extraction`` with a unique ``reply_key`` and blocks on
    ``pg_task_result`` until the executor consumer records the result or the
    timeout elapses. Honours the same contract as the SDK dispatcher: it never
    raises and converts a timeout/failure into ``ExecutionResult.failure`` so
    callers can branch on ``result.success`` identically on either transport.
    """

    def dispatch(
        self,
        context: ExecutionContext,
        timeout: int | None = None,
    ) -> ExecutionResult:
        if timeout is None:
            timeout = int(os.environ.get(_DEFAULT_TIMEOUT_ENV, _DEFAULT_TIMEOUT))
        reply_key = str(uuid.uuid4())
        queue = f"{_QUEUE_PREFIX}{context.executor_name}"
        org = getattr(context, "organization_id", "") or ""
        try:
            enqueue_task(
                task_name=_EXECUTE_TASK,
                queue=queue,
                args=[context.to_dict()],
                org_id=str(org),
                reply_key=reply_key,
            )
        except Exception as exc:
            logger.exception(
                "PG executor dispatch: enqueue failed (executor=%s run_id=%s)",
                context.executor_name,
                context.run_id,
            )
            return ExecutionResult.failure(error=f"{type(exc).__name__}: {exc}")
        logger.info(
            "PG executor dispatch: enqueued reply_key=%s queue=%s run_id=%s "
            "timeout=%ss; waiting for result...",
            reply_key,
            queue,
            context.run_id,
            timeout,
        )
        row = self._wait_for_result(reply_key, timeout)
        if row is None:
            return ExecutionResult.failure(
                error=f"TimeoutError: executor reply not received within {timeout}s"
            )
        if row.status == "completed" and row.result is not None:
            return ExecutionResult.from_dict(row.result)
        return ExecutionResult.failure(error=row.error or "executor task failed")

    @staticmethod
    def _wait_for_result(reply_key: str, timeout: float) -> PgTaskResult | None:
        """Poll ``pg_task_result`` until the row appears or *timeout* elapses.

        Poll-based with capped backoff (PgBouncer-safe; no LISTEN/NOTIFY). Each
        ``.first()`` opens+closes its own Django query so a freshly committed row
        from the executor consumer is visible.
        """
        deadline = time.monotonic() + timeout
        delay = _POLL_INITIAL_SECONDS
        while True:
            row = PgTaskResult.objects.filter(pk=reply_key).first()
            if row is not None:
                return row
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, _POLL_MAX_SECONDS)


class RoutingExecutionDispatcher:
    """Gate-routed executor dispatcher returned by ``_get_dispatcher()``.

    ``dispatch()`` chooses PG vs Celery per call (instant rollout/rollback);
    ``dispatch_async`` / ``dispatch_with_callback`` always delegate to Celery —
    the async/callback path stays on Celery until a later continuation slice.
    Duck-typed against the SDK ``ExecutionDispatcher`` so call sites are unchanged.
    """

    def __init__(self, celery_app: object | None = None) -> None:
        self._celery = ExecutionDispatcher(celery_app=celery_app)
        self._pg = PgExecutionDispatcher()

    def dispatch(
        self,
        context: ExecutionContext,
        timeout: int | None = None,
        headers: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        if resolve_executor_transport(context):
            logger.info(
                "Executor RPC → PG transport (executor=%s run_id=%s)",
                context.executor_name,
                context.run_id,
            )
            # PG carries fairness via the enqueue payload, not Celery headers, so
            # the headers (fairness key) are intentionally not forwarded here.
            return self._pg.dispatch(context, timeout=timeout)
        return self._celery.dispatch(context, timeout=timeout, headers=headers)

    def dispatch_async(
        self, context: ExecutionContext, headers: dict[str, Any] | None = None
    ) -> str:
        return self._celery.dispatch_async(context, headers=headers)

    def dispatch_with_callback(self, context: ExecutionContext, **kwargs: Any) -> Any:
        return self._celery.dispatch_with_callback(context, **kwargs)


def get_executor_dispatcher(
    celery_app: object | None = None,
) -> RoutingExecutionDispatcher:
    """Factory: the gate-routed executor dispatcher (PG when enabled, else Celery)."""
    return RoutingExecutionDispatcher(celery_app=celery_app)
