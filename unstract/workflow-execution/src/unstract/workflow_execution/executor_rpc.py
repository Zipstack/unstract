"""Shared executor-RPC dispatch — the reply_key/timeout orchestration.

The executor "RPC" is a synchronous request-reply: a caller sends an
``ExecutionContext`` to the executor worker and blocks for the ``ExecutionResult``.
Backend (Django/prompt-studio) and workers (``structure_tool``) both need it, and
used to carry **byte-for-byte mirrors** of this logic — the only thing that
genuinely differs between them is the *transport primitive*: the backend enqueues
via the Django ORM (``enqueue_task`` + ``PgTaskResult``), the workers via psycopg2
(``PgQueueClient`` + ``PgResultBackend``).

So this module owns everything transport-agnostic exactly once, and the differing
primitive is **injected** (composition, not inheritance) via :class:`QueueTransport`:

- :class:`PgExecutionDispatcher` — concrete; ``dispatch`` / ``dispatch_async`` /
  ``dispatch_with_callback`` + the reply_key/timeout orchestration and the
  never-raises contract (timeout/failure → ``ExecutionResult.failure``). It calls
  ``transport.enqueue(...)`` and ``transport.wait_for_result(...)``.

PG is the only transport. This module used to also hold ``resolve_pg_transport``
(the ``pg_queue_enabled`` Flipt gate) and ``RoutingExecutionDispatcher`` (which
picked PG-vs-Celery per call); both went with the flag in UN-4046.

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
from typing import TYPE_CHECKING, Protocol

from unstract.core.data_models import PgTaskStatus
from unstract.core.execution_dispatch import DispatchHandle, signature_to_continuation
from unstract.sdk1.execution.result import ExecutionResult

if TYPE_CHECKING:
    from unstract.core.data_models import ContinuationSpec
    from unstract.core.execution_dispatch import CallbackSignature
    from unstract.sdk1.execution.context import ExecutionContext

logger = logging.getLogger(__name__)

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
    ) -> ExecutionResult:
        """Send ``execute_extraction`` and block for the result (request-reply).

        Enqueues with a unique ``reply_key``, polls the result row until it appears
        or *timeout* elapses, and converts the outcome to an ``ExecutionResult``.
        Never raises (the SDK dispatch contract): an enqueue/poll failure, a timeout,
        or a malformed/failed/empty result all become ``ExecutionResult.failure`` so
        callers branch on ``result.success`` identically on either transport.

        No ``headers`` on any PG dispatch method: the PG path carries org/routing in
        the enqueue payload (``transport.enqueue(..., org_id=...)``), not Celery
        headers. This method takes no ``headers`` argument: callers must not pass
        one. The routing dispatcher that used to absorb a ``headers=`` kwarg went
        with the flag in UN-4046, and three call sites kept passing it — every
        extraction raised ``TypeError`` until they were fixed.
        """
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
        if row.status == PgTaskStatus.COMPLETED.value:
            # COMPLETED but result is None — a producer-side anomaly (the consumer
            # recorded success yet wrote no payload). Distinguish it from a real task
            # failure so it isn't mislabelled "executor task failed".
            logger.warning(
                "PG executor dispatch: completed row has no result "
                "(reply_key=%s run_id=%s)",
                reply_key,
                context.run_id,
            )
            return ExecutionResult.failure(
                error=f"Executor reported completion with no result (reply_key {reply_key})"
            )
        logger.warning(
            "PG executor dispatch: executor reported failure (reply_key=%s "
            "run_id=%s): %s",
            reply_key,
            context.run_id,
            row.error or "(no error)",
        )
        return ExecutionResult.failure(error=row.error or "executor task failed")

    def dispatch_async(self, context: ExecutionContext) -> str:
        """Fire-and-forget enqueue of ``execute_extraction``; returns the task id.

        No ``reply_key``, no callback, no blocking. A caller that needs the outcome
        uses :meth:`dispatch_with_callback` (a self-chained continuation), not polling
        on this id. Enqueue failures **propagate** — parity with the SDK, which lets a
        broker error out of ``dispatch_async`` — but are logged here first so the
        failure is observable even if the caller swallows it.
        """
        task_id = str(uuid.uuid4())
        queue = f"{QUEUE_PREFIX}{context.executor_name}"
        org = str(getattr(context, "organization_id", "") or "")
        try:
            self._transport.enqueue(
                queue=queue, context=context, org_id=org, task_id=task_id
            )
        except Exception:
            # The enqueue is the only fallible step (fire-and-forget). Log before the
            # re-raise so a swallowed error is still observable.
            logger.exception(
                "PG executor dispatch_async: enqueue failed (executor=%s run_id=%s)",
                context.executor_name,
                context.run_id,
            )
            raise
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
        on_success: CallbackSignature | None = None,
        on_error: CallbackSignature | None = None,
        task_id: str | None = None,
    ) -> DispatchHandle:
        """Fire-and-forget enqueue with self-chained callbacks (§5 model).

        Instead of Celery ``link`` / ``link_error``, the on-success / on-error Celery
        ``Signature``s are translated to serialisable ``ContinuationSpec``s and
        carried in the payload; after the executor runs, the consumer self-chains the
        matching continuation. Returns a :class:`DispatchHandle` exposing ``.id``
        (== ``task_id``) so call sites read the task id exactly as on the Celery path.

        Enqueue failures **propagate** (parity with :meth:`dispatch_async`), logged
        first. NOTE: because the continuations are carried *in the payload*, a failed
        enqueue means the executor never runs and ``on_error`` never fires — so a
        caller MUST treat a raised enqueue as the failure signal itself (the
        prompt-studio views do, in their own try/except).
        """
        task_id = task_id or str(uuid.uuid4())
        queue = f"{QUEUE_PREFIX}{context.executor_name}"
        org = str(getattr(context, "organization_id", "") or "")
        success_spec = signature_to_continuation(on_success)
        error_spec = signature_to_continuation(on_error)
        try:
            self._transport.enqueue(
                queue=queue,
                context=context,
                org_id=org,
                on_success=success_spec,
                on_error=error_spec,
                task_id=task_id,
            )
        except Exception:
            logger.exception(
                "PG executor dispatch_with_callback: enqueue failed — on_error will "
                "NOT fire (executor=%s run_id=%s)",
                context.executor_name,
                context.run_id,
            )
            raise
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
