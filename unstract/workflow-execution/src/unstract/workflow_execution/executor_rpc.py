"""Shared executor-RPC dispatch for the PG path — the gate + reply_key orchestration.

The executor "RPC" is a synchronous request-reply: a caller sends an
``ExecutionContext`` to the executor worker and blocks for the ``ExecutionResult``.
The legacy transport is Celery (the SDK ``ExecutionDispatcher``); the PG path adds a
parallel Postgres transport. Backend (Django/prompt-studio) and workers
(``structure_tool``) both need it, and used to carry **byte-for-byte mirrors** of
this logic — the only thing that genuinely differs between them is the *transport
primitive*: the backend enqueues via the Django ORM (``enqueue_task`` +
``PgTaskResult``), the workers via psycopg2 (``PgQueueClient`` + ``PgResultBackend``).

So this module owns everything transport-agnostic exactly once, and the differing
primitive is **injected** (composition, not inheritance) via :class:`QueueTransport`:

- :class:`PgExecutionDispatcher` — concrete; ``dispatch`` / ``dispatch_async`` /
  ``dispatch_with_callback`` + the reply_key/timeout orchestration and the
  never-raises contract (timeout/failure → ``ExecutionResult.failure``). It calls
  ``transport.enqueue(...)`` and ``transport.wait_for_result(...)``.
- :func:`resolve_pg_transport` — the gate: a master kill-switch (its boolean value
  supplied by the caller — a Django setting on the backend, an env var on the
  workers) then the single ``pg_queue_enabled`` Flipt flag, bucketed per org. Fails
  closed to Celery.
- :class:`RoutingExecutionDispatcher` — picks PG-vs-Celery per call (instant
  rollout/rollback) for every mode; the Celery dispatcher, the PG dispatcher and the
  per-side ``resolve`` are all injected.

It lives in ``unstract-workflow-execution`` (which both backend and workers already
depend on) rather than ``unstract.core`` because it needs ``unstract.sdk1`` and
``sdk1`` imports ``core`` — hosting it in ``core`` would be circular. It has no
Django/psycopg2 dependency: those live entirely in the injected transport.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from unstract.core.data_models import PgTaskStatus
from unstract.core.execution_dispatch import DispatchHandle, signature_to_continuation
from unstract.flags.feature_flag import check_feature_flag_status
from unstract.sdk1.execution.result import ExecutionResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from unstract.core.data_models import ContinuationSpec
    from unstract.sdk1.execution.context import ExecutionContext

logger = logging.getLogger(__name__)

# The single PG-queue rollout flag — the same key execution and the scheduler read,
# so one flip turns the whole PG-queue feature on/off.
PG_QUEUE_FLAG_KEY = "pg_queue_enabled"
EXECUTE_TASK = "execute_extraction"
# Mirror the SDK's queue-per-executor convention so the PG executor queue name
# matches the Celery one (the worker-pg-executor consumer subscribes to these).
QUEUE_PREFIX = "celery_executor_"
# Caller-side wait default — mirrors the SDK dispatcher (EXECUTOR_RESULT_TIMEOUT env,
# else 3600s) so a PG-routed caller waits exactly as long as a Celery one.
DEFAULT_TIMEOUT_ENV = "EXECUTOR_RESULT_TIMEOUT"
DEFAULT_TIMEOUT = 3600


@dataclass
class ExecResultRow:
    """Normalised executor-RPC result row — the transport-agnostic shape
    :meth:`PgExecutionDispatcher.dispatch` interprets.

    The backend's result row is a Django model (attribute access) and the workers'
    is a ``dict``; both fold to this so ``dispatch`` has one code path. Every field
    defaults to ``None`` — the never-raises contract must not depend on the producer
    having written every key.
    """

    status: str | None = None
    result: dict | None = None
    error: str | None = None


class QueueTransport(Protocol):
    """The per-side primitive the shared dispatcher needs — the ONLY thing that
    differs between backend and workers.

    ``enqueue`` writes one ``execute_extraction`` request-row (the optional keys
    select the dispatch shape: ``reply_key`` → request-reply; ``on_success`` /
    ``on_error`` / ``task_id`` → async/callback). ``wait_for_result`` polls for the
    reply and returns a normalised :class:`ExecResultRow` (or ``None`` on timeout).
    """

    def enqueue(
        self,
        *,
        queue: str,
        context: ExecutionContext,
        org_id: str,
        reply_key: str | None = None,
        on_success: ContinuationSpec | None = None,
        on_error: ContinuationSpec | None = None,
        task_id: str | None = None,
    ) -> None: ...

    def wait_for_result(self, reply_key: str, timeout: float) -> ExecResultRow | None: ...


def resolve_pg_transport(
    context: ExecutionContext,
    *,
    master_gate_enabled: bool,
    flag_key: str = PG_QUEUE_FLAG_KEY,
) -> bool:
    """True → route this executor dispatch over PG; False → Celery (default).

    Master-gated by ``master_gate_enabled`` (the caller supplies its value — a Django
    setting on the backend, an env var on the workers), then the single
    ``pg_queue_enabled`` Flipt flag, bucketed per org. **Fails closed to Celery** on a
    closed gate, a blind Flipt, or any error — so the executor never silently loses
    its transport.
    """
    if not master_gate_enabled:
        return False
    if os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() != "true":
        logger.warning(
            "resolve_pg_transport: gate ON but FLIPT_SERVICE_AVAILABLE != true "
            "(Flipt blind); using Celery"
        )
        return False
    org = getattr(context, "organization_id", None)
    # %-bucket keyed on org; fall back to run_id so a context without an org still
    # resolves deterministically.
    entity_id = str(org or getattr(context, "run_id", "") or "default")
    flag_context = {"executor_name": str(context.executor_name)}
    if org:
        flag_context["organization_id"] = str(org)
    try:
        enabled = check_feature_flag_status(
            flag_key=flag_key, entity_id=entity_id, context=flag_context
        )
    except Exception:
        logger.warning(
            "resolve_pg_transport: Flipt check failed; using Celery", exc_info=True
        )
        return False
    return bool(enabled)


def _resolve_timeout(timeout: int | None) -> int:
    """Caller timeout, defaulting to ``EXECUTOR_RESULT_TIMEOUT`` env then 3600s.

    Guarded so a misconfigured env value can't raise out of ``dispatch`` (the
    never-raises contract) — it logs and falls back instead of silently waiting the
    full default with no signal.
    """
    if timeout is not None:
        return timeout
    try:
        return int(os.environ.get(DEFAULT_TIMEOUT_ENV, DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        logger.warning(
            "PG executor dispatch: invalid %s=%r; falling back to %ss",
            DEFAULT_TIMEOUT_ENV,
            os.environ.get(DEFAULT_TIMEOUT_ENV),
            DEFAULT_TIMEOUT,
        )
        return DEFAULT_TIMEOUT


class PgExecutionDispatcher:
    """PG request-reply executor dispatch — drop-in for the SDK dispatch contract.

    Concrete + transport-injected: enqueues ``execute_extraction`` with a unique
    ``reply_key`` and blocks on the result row until the executor consumer records it
    or the timeout elapses. Honours the SDK dispatcher contract: it never raises and
    converts a timeout/failure into ``ExecutionResult.failure`` so callers branch on
    ``result.success`` identically on either transport.
    """

    def __init__(self, transport: QueueTransport) -> None:
        self._transport = transport

    def dispatch(
        self,
        context: ExecutionContext,
        timeout: int | None = None,
        headers: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        # ``headers`` is accepted (and ignored) for substitutability with the SDK /
        # Routing shapes — the PG path carries org/routing via the enqueue payload,
        # not Celery headers, so fairness headers are intentionally not forwarded.
        timeout = _resolve_timeout(timeout)
        reply_key = str(uuid.uuid4())
        queue = f"{QUEUE_PREFIX}{context.executor_name}"
        org = str(getattr(context, "organization_id", "") or "")
        try:
            self._transport.enqueue(
                queue=queue, context=context, org_id=org, reply_key=reply_key
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
        try:
            row = self._transport.wait_for_result(reply_key, timeout)
        except Exception as exc:
            # Honour the never-raises contract even if the poll connection dies.
            logger.exception(
                "PG executor dispatch: wait failed (reply_key=%s run_id=%s)",
                reply_key,
                context.run_id,
            )
            return ExecutionResult.failure(error=f"{type(exc).__name__}: {exc}")
        if row is None:
            # On timeout the executor task may still be running on the consumer; it
            # writes its outcome under this reply_key, but we've given up reading it
            # (the reaper retention-sweeps the orphan row). A retry re-dispatches with
            # a FRESH reply_key — at-least-once + caller-timeout by design.
            logger.warning(
                "PG executor dispatch: TIMEOUT after %ss (reply_key=%s run_id=%s) — "
                "the executor task may still be running",
                timeout,
                reply_key,
                context.run_id,
            )
            return ExecutionResult.failure(
                error=f"TimeoutError: executor reply not received within {timeout}s"
            )
        if row.status == PgTaskStatus.COMPLETED.value and row.result is not None:
            try:
                return ExecutionResult.from_dict(row.result)
            except Exception as exc:
                # A malformed completed row becomes a failure result, not a raise.
                # Surface the parse cause so a UI reading result.error isn't left with
                # an opaque message.
                logger.exception(
                    "PG executor dispatch: malformed completed result "
                    "(reply_key=%s run_id=%s)",
                    reply_key,
                    context.run_id,
                )
                return ExecutionResult.failure(
                    error=(
                        f"Malformed executor result ({type(exc).__name__}) "
                        f"for reply_key {reply_key}"
                    )
                )
        logger.warning(
            "PG executor dispatch: executor reported failure (reply_key=%s "
            "run_id=%s): %s",
            reply_key,
            context.run_id,
            row.error or "(no error)",
        )
        return ExecutionResult.failure(error=row.error or "executor task failed")

    def dispatch_async(
        self, context: ExecutionContext, headers: dict[str, Any] | None = None
    ) -> str:
        """Fire-and-forget enqueue of ``execute_extraction``; returns the task id.

        No ``reply_key``, no callback, no blocking. A caller that needs the outcome
        uses :meth:`dispatch_with_callback` (a self-chained continuation), not polling
        on this id. ``headers`` is accepted and ignored (PG carries routing in the
        payload). Enqueue failures propagate — parity with the SDK, which lets a
        broker error out of ``dispatch_async``.
        """
        task_id = str(uuid.uuid4())
        queue = f"{QUEUE_PREFIX}{context.executor_name}"
        org = str(getattr(context, "organization_id", "") or "")
        self._transport.enqueue(queue=queue, context=context, org_id=org, task_id=task_id)
        logger.info(
            "PG executor dispatch_async: enqueued task_id=%s queue=%s run_id=%s",
            task_id,
            queue,
            context.run_id,
        )
        return task_id

    def dispatch_with_callback(
        self,
        context: ExecutionContext,
        on_success: Any | None = None,
        on_error: Any | None = None,
        task_id: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> DispatchHandle:
        """Fire-and-forget enqueue with self-chained callbacks (§5 model).

        Instead of Celery ``link`` / ``link_error``, the on-success / on-error Celery
        ``Signature``s are translated to serialisable ``ContinuationSpec``s and
        carried in the payload; after the executor runs, the consumer self-chains the
        matching continuation. Returns a :class:`DispatchHandle` exposing ``.id``
        (== ``task_id``) so call sites read the task id exactly as on the Celery path.
        """
        task_id = task_id or str(uuid.uuid4())
        queue = f"{QUEUE_PREFIX}{context.executor_name}"
        org = str(getattr(context, "organization_id", "") or "")
        success_spec = signature_to_continuation(on_success)
        error_spec = signature_to_continuation(on_error)
        self._transport.enqueue(
            queue=queue,
            context=context,
            org_id=org,
            on_success=success_spec,
            on_error=error_spec,
            task_id=task_id,
        )
        logger.info(
            "PG executor dispatch_with_callback: enqueued task_id=%s queue=%s "
            "run_id=%s on_success=%s on_error=%s",
            task_id,
            queue,
            context.run_id,
            success_spec["task_name"] if success_spec else None,
            error_spec["task_name"] if error_spec else None,
        )
        return DispatchHandle(task_id)


class RoutingExecutionDispatcher:
    """Gate-routed executor dispatcher: every mode picks PG vs Celery per call
    (read at dispatch time → flipping the flag is an instant, no-redeploy
    rollout/rollback). Duck-typed against the SDK ``ExecutionDispatcher`` so call
    sites are unchanged.

    Composition-injected: the Celery dispatcher (``celery``), the PG dispatcher
    (``pg``) and the per-side gate (``resolve(context) -> bool``).
    """

    def __init__(
        self,
        *,
        celery: Any,
        pg: PgExecutionDispatcher,
        resolve: Callable[[ExecutionContext], bool],
    ) -> None:
        self._celery = celery
        self._pg = pg
        self._resolve = resolve

    def dispatch(
        self,
        context: ExecutionContext,
        timeout: int | None = None,
        headers: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        if self._resolve(context):
            logger.info(
                "Executor RPC → PG transport (executor=%s run_id=%s)",
                context.executor_name,
                context.run_id,
            )
            # PG carries org/routing via the enqueue payload, not Celery headers, so
            # the fairness headers are intentionally not forwarded here.
            return self._pg.dispatch(context, timeout=timeout)
        return self._celery.dispatch(context, timeout=timeout, headers=headers)

    def dispatch_async(
        self, context: ExecutionContext, headers: dict[str, Any] | None = None
    ) -> str:
        if self._resolve(context):
            return self._pg.dispatch_async(context)
        return self._celery.dispatch_async(context, headers=headers)

    def dispatch_with_callback(
        self,
        context: ExecutionContext,
        on_success: Any | None = None,
        on_error: Any | None = None,
        task_id: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> Any:
        if self._resolve(context):
            return self._pg.dispatch_with_callback(
                context, on_success=on_success, on_error=on_error, task_id=task_id
            )
        return self._celery.dispatch_with_callback(
            context,
            on_success=on_success,
            on_error=on_error,
            task_id=task_id,
            headers=headers,
        )
