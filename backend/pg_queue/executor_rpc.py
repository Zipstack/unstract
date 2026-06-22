"""Executor-RPC for the PG path — backend (Django) transport adapter.

The gate + reply_key/timeout orchestration + routing live ONCE in
``unstract.workflow_execution.executor_rpc`` (shared with the workers). This module
is the thin Django half: a :class:`DjangoQueueTransport` that enqueues via the ORM
(``enqueue_task``) and polls ``PgTaskResult``, plus the per-side gate (master switch =
``settings.PG_QUEUE_TRANSPORT_ENABLED``) and the :func:`get_executor_dispatcher`
factory that wires them together.

Zero-regression: gate off ⇒ the routing dispatcher delegates every mode to the
unchanged Celery ``ExecutionDispatcher`` and no ``pg_task_result`` row is created.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import close_old_connections

from pg_queue.models import PgTaskResult
from pg_queue.producer import enqueue_task
from unstract.core.polling import poll_for_row
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.workflow_execution.executor_rpc import (
    EXECUTE_TASK,
    ExecResultRow,
    PgExecutionDispatcher,
    QueueTransport,
    RoutingExecutionDispatcher,
    resolve_pg_transport,
)

if TYPE_CHECKING:
    from unstract.core.data_models import ContinuationSpec
    from unstract.sdk1.execution.context import ExecutionContext

# Re-exported so existing ``from pg_queue.executor_rpc import …`` imports keep working.
__all__ = [
    "DjangoQueueTransport",
    "PgExecutionDispatcher",
    "RoutingExecutionDispatcher",
    "get_executor_dispatcher",
    "resolve_executor_transport",
]


def resolve_executor_transport(context: ExecutionContext) -> bool:
    """True → route this executor dispatch over PG; False → Celery (default).

    The backend gate: master switch ``settings.PG_QUEUE_TRANSPORT_ENABLED``, then the
    shared Flipt eval (single ``pg_queue_enabled`` flag, fail-closed).
    """
    return resolve_pg_transport(
        context, master_gate_enabled=settings.PG_QUEUE_TRANSPORT_ENABLED
    )


class DjangoQueueTransport(QueueTransport):
    """:class:`QueueTransport` over the Django ORM (the backend half).

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
        enqueue_task(
            task_name=EXECUTE_TASK,
            queue=queue,
            args=[context.to_dict()],
            org_id=org_id,
            reply_key=reply_key,
            on_success=on_success,
            on_error=on_error,
            task_id=task_id,
        )

    def wait_for_result(self, reply_key: str, timeout: float) -> ExecResultRow | None:
        """Poll ``pg_task_result`` until the row appears or *timeout* elapses.

        Uses the shared :func:`poll_for_row` backoff skeleton, releasing the DB
        connection between polls (``close_old_connections``) so a long-running RPC
        does not pin a backend connection and exhaust the pool. Each poll is its own
        autocommit query, so a row committed by the executor consumer becomes visible
        — **dispatch must NOT be called inside an open transaction**
        (``transaction.atomic`` / ``ATOMIC_REQUESTS`` would pin one snapshot and never
        see the new row).
        """

        def _fetch() -> ExecResultRow | None:
            row = PgTaskResult.objects.filter(pk=reply_key).first()
            if row is None:
                return None
            return ExecResultRow(status=row.status, result=row.result, error=row.error)

        return poll_for_row(_fetch, timeout, between_polls=close_old_connections)


def get_executor_dispatcher(
    celery_app: object | None = None,
) -> RoutingExecutionDispatcher:
    """Factory: the gate-routed executor dispatcher (PG when enabled, else Celery)."""
    return RoutingExecutionDispatcher(
        celery=ExecutionDispatcher(celery_app=celery_app),
        pg=PgExecutionDispatcher(DjangoQueueTransport()),
        resolve=resolve_executor_transport,
    )
