"""Executor-RPC for the PG path — workers (psycopg2) transport adapter.

The gate + reply_key/timeout orchestration + routing live ONCE in
``unstract.workflow_execution.executor_rpc`` (shared with the backend). This module
is the thin psycopg2 half: a :class:`PgClientQueueTransport` that enqueues via
:class:`~queue_backend.pg_queue.client.PgQueueClient` and polls via
:class:`~queue_backend.pg_queue.result_backend.PgResultBackend`, plus the per-side
gate (master switch = the ``PG_QUEUE_TRANSPORT_ENABLED`` env, the workers analogue of
the backend's Django setting) and the :func:`get_executor_dispatcher` factory.

Zero-regression: gate off ⇒ the routing dispatcher delegates every mode to the
unchanged Celery ``ExecutionDispatcher`` and no ``pg_task_result`` row is created.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.workflow_execution.executor_rpc import (
    EXECUTE_TASK,
    ExecResultRow,
    PgExecutionDispatcher,
    QueueTransport,
    RoutingExecutionDispatcher,
    resolve_pg_transport,
)

from .client import PgQueueClient
from .result_backend import PgResultBackend
from .task_payload import to_payload

if TYPE_CHECKING:
    from unstract.core.data_models import ContinuationSpec
    from unstract.sdk1.execution.context import ExecutionContext

# Re-exported so existing ``from queue_backend.pg_queue.executor_rpc import …``
# imports keep working.
__all__ = [
    "PgClientQueueTransport",
    "PgExecutionDispatcher",
    "RoutingExecutionDispatcher",
    "get_executor_dispatcher",
    "resolve_executor_transport",
]

logger = logging.getLogger(__name__)

# Master kill-switch + deploy-ordering gate — the workers analogue of the backend's
# ``settings.PG_QUEUE_TRANSPORT_ENABLED``, read straight from the env here.
_MASTER_GATE_ENV = "PG_QUEUE_TRANSPORT_ENABLED"
_TRUE = "true"
_FALSE = "false"


def resolve_executor_transport(context: ExecutionContext) -> bool:
    """True → route this executor dispatch over PG; False → Celery (default).

    The workers gate: master switch = the ``PG_QUEUE_TRANSPORT_ENABLED`` env, then the
    shared Flipt eval (single ``pg_queue_enabled`` flag, fail-closed).
    """
    raw = os.environ.get(_MASTER_GATE_ENV, _FALSE)
    master = raw.strip().lower() == _TRUE
    if not master and raw.strip().lower() != _FALSE:
        # A fat-fingered value ("1"/"yes"/"on"/" True ") parses to OFF — warn so it
        # isn't a silent no-op for an operator who expected it to enable PG.
        logger.warning(
            "resolve_executor_transport: %s=%r is not 'true'/'false' — treating as "
            "OFF (PG transport disabled); use exactly 'true' to enable",
            _MASTER_GATE_ENV,
            raw,
        )
    return resolve_pg_transport(context, master_gate_enabled=master)


class PgClientQueueTransport(QueueTransport):
    """:class:`QueueTransport` over psycopg2 (the workers half).

    Inherits the Protocol so a type-checker verifies this implementation against the
    seam independently of the ``PgExecutionDispatcher(...)`` construction site.
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
    ) -> None:
        # A short-lived client owns its connection for just the insert (which commits
        # internally) so the message is durably visible to the worker-pg-executor
        # consumer before we begin polling — and no connection is pinned for the whole
        # (possibly long) RPC.
        payload = to_payload(
            EXECUTE_TASK,
            args=[context.to_dict()],
            queue=queue,
            reply_key=reply_key,
            on_success=on_success,
            on_error=on_error,
            task_id=task_id,
        )
        with PgQueueClient() as client:
            client.send(queue, payload, org_id=org_id)

    def wait_for_result(self, reply_key: str, timeout: float) -> ExecResultRow | None:
        """Poll ``pg_task_result`` until the row appears or *timeout* elapses.

        ``PgResultBackend`` owns one connection for the duration of the wait and
        closes it on exit, so a long RPC never leaks a connection. The result row is a
        ``{status, result, error}`` dict; fold it to the shared :class:`ExecResultRow`.
        """
        with PgResultBackend() as rb:
            row = rb.wait_for_result(reply_key, timeout)
        if row is None:
            return None
        return ExecResultRow(
            status=row.get("status"), result=row.get("result"), error=row.get("error")
        )


def get_executor_dispatcher(
    celery_app: object | None = None,
) -> RoutingExecutionDispatcher:
    """Factory: the gate-routed executor dispatcher (PG when enabled, else Celery)."""
    return RoutingExecutionDispatcher(
        celery=ExecutionDispatcher(celery_app=celery_app),
        pg=PgExecutionDispatcher(PgClientQueueTransport()),
        resolve=resolve_executor_transport,
    )
