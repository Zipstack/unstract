"""Executor-RPC transport routing for the PG path — workers side (Phase 9, ③b-2).

The workers-side twin of ``backend/pg_queue/executor_rpc.py``. The executor "RPC"
is a synchronous request-reply: a caller (here, the ``structure_tool`` task in the
file_processing worker) sends an ``ExecutionContext`` to the executor worker and
blocks for the ``ExecutionResult``. The legacy transport is Celery — the SDK
``ExecutionDispatcher`` (``send_task`` + ``AsyncResult.get``). This module adds a
**parallel** Postgres transport that leaves Celery and the SDK completely
untouched (no SDK edit, no change to the ``execute_extraction`` task or the Celery
executor worker):

- :class:`PgExecutionDispatcher` enqueues ``execute_extraction`` onto the PG queue
  (via :class:`~queue_backend.pg_queue.client.PgQueueClient`) with a unique
  ``reply_key`` and polls ``pg_task_result`` (via
  :class:`~queue_backend.pg_queue.result_backend.PgResultBackend`) for the reply —
  same ``.dispatch()`` contract as the SDK dispatcher (never raises;
  failure/timeout → ``ExecutionResult.failure``). The already-running
  ``worker-pg-executor`` consumer runs the task and writes the reply, so this side
  only adds the enqueue + poll halves.
- :func:`resolve_executor_transport` is the gate: master
  ``PG_QUEUE_TRANSPORT_ENABLED`` (env, the workers analogue of the backend's
  Django setting) then the **single** Flipt flag ``pg_queue_enabled`` — the same
  flag the execution path uses, so one flip turns the whole PG-queue feature
  on/off. Fails closed to Celery.
- :class:`RoutingExecutionDispatcher` is what ``structure_tool`` gets from
  :func:`get_executor_dispatcher`: ``dispatch()`` picks PG-vs-Celery **per call**
  (read at dispatch time → flipping the flag is an instant, no-redeploy
  rollout/rollback); ``dispatch_async`` / ``dispatch_with_callback`` always
  delegate to Celery (the callback path is a later slice).

Zero-regression: gate off ⇒ every method delegates to the unchanged Celery
``ExecutionDispatcher`` and no ``pg_task_result`` row is created.

TODO(shared): ``resolve_executor_transport`` and the reply_key/poll orchestration
mirror the backend module almost verbatim — only the transport primitives differ
(psycopg2 here vs Django ORM there). A later slice can lift the shared logic into
``unstract.core`` so the gate/contract lives in one place.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING, Any

from unstract.core.data_models import ContinuationSpec, PgTaskStatus
from unstract.core.execution_dispatch import DispatchHandle, signature_to_continuation
from unstract.flags.feature_flag import check_feature_flag_status
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.result import ExecutionResult

from .client import PgQueueClient
from .result_backend import PgResultBackend
from .task_payload import to_payload

if TYPE_CHECKING:
    from unstract.sdk1.execution.context import ExecutionContext

logger = logging.getLogger(__name__)

# The single PG-queue rollout flag — same key the execution path and scheduler
# read. Defined in backend/pg_queue/flags.py too; kept as a literal here because
# workers can't import backend code (see TODO(shared) in the module docstring).
PG_QUEUE_FLAG_KEY = "pg_queue_enabled"
# Master kill-switch + deploy-ordering gate. The workers analogue of the backend's
# ``settings.PG_QUEUE_TRANSPORT_ENABLED`` — read straight from the env here.
_MASTER_GATE_ENV = "PG_QUEUE_TRANSPORT_ENABLED"

_EXECUTE_TASK = "execute_extraction"
# Mirror the SDK's queue-per-executor convention so the PG executor queue name
# matches the Celery one (the worker-pg-executor consumer subscribes to these).
_QUEUE_PREFIX = "celery_executor_"
# Caller-side wait default — mirrors the SDK dispatcher (EXECUTOR_RESULT_TIMEOUT
# env, else 3600s) so a PG-routed caller waits exactly as long as a Celery one.
_DEFAULT_TIMEOUT_ENV = "EXECUTOR_RESULT_TIMEOUT"
_DEFAULT_TIMEOUT = 3600


def resolve_executor_transport(context: ExecutionContext) -> bool:
    """True → route this executor dispatch over PG; False → Celery (default).

    Mirrors the backend ``resolve_executor_transport``: master-gated by the
    ``PG_QUEUE_TRANSPORT_ENABLED`` env, then the **single** ``pg_queue_enabled``
    Flipt flag (shared across the whole PG-queue feature), bucketed per org.
    **Fails closed to Celery** on a closed gate, a blind Flipt, or any error — so
    the executor never silently loses its transport.
    """
    if os.environ.get(_MASTER_GATE_ENV, "false").lower() != "true":
        return False
    if os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() != "true":
        logger.warning(
            "resolve_executor_transport: gate ON but FLIPT_SERVICE_AVAILABLE != "
            "true (Flipt blind); using Celery"
        )
        return False
    org = getattr(context, "organization_id", None)
    # %-bucket keyed on org; fall back to run_id so a context without an org still
    # resolves deterministically (mirrors the backend resolver).
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
        headers: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        # ``headers`` is accepted (and ignored) for substitutability with the SDK
        # ``ExecutionDispatcher.dispatch`` / ``RoutingExecutionDispatcher.dispatch``
        # shapes — the PG path carries org/routing via the enqueue payload, not
        # Celery headers, so fairness headers are intentionally not forwarded.
        if timeout is None:
            # Guard the env parse so a misconfigured EXECUTOR_RESULT_TIMEOUT can't
            # raise out of dispatch() (the never-raises contract).
            try:
                timeout = int(os.environ.get(_DEFAULT_TIMEOUT_ENV, _DEFAULT_TIMEOUT))
            except (TypeError, ValueError):
                # Don't swallow silently — an operator who fat-fingers the value
                # would otherwise wait the 3600s default with no signal.
                logger.warning(
                    "PG executor dispatch: invalid %s=%r; falling back to %ss",
                    _DEFAULT_TIMEOUT_ENV,
                    os.environ.get(_DEFAULT_TIMEOUT_ENV),
                    _DEFAULT_TIMEOUT,
                )
                timeout = _DEFAULT_TIMEOUT
        reply_key = str(uuid.uuid4())
        queue = f"{_QUEUE_PREFIX}{context.executor_name}"
        org = str(getattr(context, "organization_id", "") or "")
        try:
            self._enqueue(queue, context, org, reply_key=reply_key)
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
            row = self._wait_for_result(reply_key, timeout)
        except Exception as exc:
            # Honour the never-raises contract even if the poll connection dies.
            logger.exception(
                "PG executor dispatch: wait failed (reply_key=%s run_id=%s)",
                reply_key,
                context.run_id,
            )
            return ExecutionResult.failure(error=f"{type(exc).__name__}: {exc}")
        if row is None:
            # On timeout the executor task may still be running on the consumer;
            # it will write its outcome under this reply_key, but we've already
            # given up reading it (the reaper retention-sweeps the orphan row). If
            # the workflow engine retries the file execution, it re-dispatches with
            # a FRESH reply_key — so two executor tasks for the same file can
            # overlap (double LLM spend / duplicate writes). De-duping that belongs
            # at the file-execution layer, not here; this transport stays at-least-
            # once + caller-timeout by design.
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
        # ``.get`` (not ``[...]``) so a result row missing ``status`` can't raise
        # out of dispatch() — the never-raises contract must not depend on the
        # producer always writing every key.
        if (
            row.get("status") == PgTaskStatus.COMPLETED.value
            and row.get("result") is not None
        ):
            try:
                return ExecutionResult.from_dict(row["result"])
            except Exception as exc:
                # A malformed completed row becomes a failure result, not a raise.
                # Surface the parse cause (like the enqueue/wait paths) so a UI
                # reading result.error isn't left with an opaque message.
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
            row.get("error") or "(no error)",
        )
        return ExecutionResult.failure(error=row.get("error") or "executor task failed")

    def dispatch_async(
        self, context: ExecutionContext, headers: dict[str, Any] | None = None
    ) -> str:
        """Fire-and-forget enqueue of ``execute_extraction``; returns the task id.

        The PG analogue of the SDK ``dispatch_async``: no ``reply_key``, no
        callback, no blocking. There is no PG ``AsyncResult`` backend, so a caller
        that needs the outcome uses :meth:`dispatch_with_callback` (a self-chained
        continuation), not polling on this id. ``headers`` is accepted and ignored
        for substitutability (PG carries routing in the payload, not Celery
        headers). Enqueue failures propagate — parity with the SDK, which lets a
        broker error out of ``dispatch_async``.
        """
        task_id = str(uuid.uuid4())
        queue = f"{_QUEUE_PREFIX}{context.executor_name}"
        org = str(getattr(context, "organization_id", "") or "")
        self._enqueue(queue, context, org, task_id=task_id)
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

        The PG analogue of the SDK ``dispatch_with_callback``: instead of Celery
        ``link`` / ``link_error`` (which the broker fires), the on-success /
        on-error Celery ``Signature``s are translated to serialisable
        :class:`ContinuationSpec`s and carried in the payload. After the executor
        consumer runs ``execute_extraction`` it self-chains the matching
        continuation onto the callback queue. Returns a :class:`DispatchHandle`
        exposing ``.id`` (== ``task_id``) so call sites read the task id exactly
        as on the Celery path. ``headers`` is accepted and ignored (see
        :meth:`dispatch_async`).
        """
        task_id = task_id or str(uuid.uuid4())
        queue = f"{_QUEUE_PREFIX}{context.executor_name}"
        org = str(getattr(context, "organization_id", "") or "")
        success_spec = signature_to_continuation(on_success)
        error_spec = signature_to_continuation(on_error)
        self._enqueue(
            queue,
            context,
            org,
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

    @staticmethod
    def _enqueue(
        queue: str,
        context: ExecutionContext,
        org_id: str,
        *,
        reply_key: str | None = None,
        on_success: ContinuationSpec | None = None,
        on_error: ContinuationSpec | None = None,
        task_id: str | None = None,
    ) -> None:
        """Enqueue an ``execute_extraction`` message (request-reply or callback).

        A short-lived client owns its connection for just the insert (which
        commits internally) so the message is durably visible to the
        ``worker-pg-executor`` consumer before we begin polling — and no
        connection is pinned for the whole (possibly long) RPC. The optional keys
        select the dispatch shape: ``reply_key`` → request-reply; ``on_success`` /
        ``on_error`` / ``task_id`` → async/callback (self-chained).
        """
        payload = to_payload(
            _EXECUTE_TASK,
            args=[context.to_dict()],
            queue=queue,
            reply_key=reply_key,
            on_success=on_success,
            on_error=on_error,
            task_id=task_id,
        )
        with PgQueueClient() as client:
            client.send(queue, payload, org_id=org_id)

    @staticmethod
    def _wait_for_result(reply_key: str, timeout: float) -> dict[str, Any] | None:
        """Poll ``pg_task_result`` until the row appears or *timeout* elapses.

        Poll-based with capped backoff (PgBouncer-safe; no LISTEN/NOTIFY). The
        backend owns one connection for the duration of the wait and closes it on
        exit, so a long RPC never leaks a connection. The pin is bounded: a
        file_processing worker runs ``--pool=prefork`` with
        ``WORKER_FILE_PROCESSING_CONCURRENCY`` (default 4) processes, and each
        dispatches sequentially, so at most ~concurrency connections are held for
        up to ``EXECUTOR_RESULT_TIMEOUT``. (The backend twin instead releases via
        ``close_old_connections`` between polls; if file_processing concurrency is
        raised materially, do the same here.)
        """
        with PgResultBackend() as rb:
            return rb.wait_for_result(reply_key, timeout)


class RoutingExecutionDispatcher:
    """Gate-routed executor dispatcher returned by :func:`get_executor_dispatcher`.

    Every mode chooses PG vs Celery per call (instant rollout/rollback):
    ``dispatch()`` (request-reply), ``dispatch_async`` (fire-and-forget) and
    ``dispatch_with_callback`` (self-chained callbacks). Duck-typed against the SDK
    ``ExecutionDispatcher`` so call sites are unchanged.
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
            # PG carries org/routing via the enqueue payload, not Celery headers,
            # so the fairness headers are intentionally not forwarded here (parity
            # with the backend executor RPC).
            return self._pg.dispatch(context, timeout=timeout)
        return self._celery.dispatch(context, timeout=timeout, headers=headers)

    def dispatch_async(
        self, context: ExecutionContext, headers: dict[str, Any] | None = None
    ) -> str:
        if resolve_executor_transport(context):
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
        if resolve_executor_transport(context):
            return self._pg.dispatch_with_callback(
                context,
                on_success=on_success,
                on_error=on_error,
                task_id=task_id,
            )
        return self._celery.dispatch_with_callback(
            context,
            on_success=on_success,
            on_error=on_error,
            task_id=task_id,
            headers=headers,
        )


def get_executor_dispatcher(
    celery_app: object | None = None,
) -> RoutingExecutionDispatcher:
    """Factory: the gate-routed executor dispatcher (PG when enabled, else Celery)."""
    return RoutingExecutionDispatcher(celery_app=celery_app)
