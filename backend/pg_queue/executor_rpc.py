"""Executor-RPC for the PG path — backend (Django) transport adapter.

The reply_key/timeout orchestration lives ONCE in
``unstract.workflow_execution.executor_rpc`` (shared with the workers). This module
is the thin Django half: a :class:`DjangoQueueTransport` that enqueues via the ORM
(``enqueue_task``) and polls ``PgTaskResult``, plus the :func:`get_executor_dispatcher`
factory that wires them together.

Since UN-4046 the factory returns the PG dispatcher unconditionally: there is no
gate, no routing dispatcher and no Celery fall-through, so a ``pg_task_result``
row is written on every request-reply dispatch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import close_old_connections

from pg_queue.models import PgTaskResult
from pg_queue.producer import enqueue_task
from unstract.core.polling import poll_for_row
from unstract.workflow_execution.executor_rpc import (
    EXECUTE_TASK,
    ExecResultRow,
    PgExecutionDispatcher,
    QueueTransport,
)

if TYPE_CHECKING:
    from unstract.core.data_models import ContinuationSpec
    from unstract.sdk1.execution.context import ExecutionContext

logger = logging.getLogger(__name__)

# Re-exported so existing ``from pg_queue.executor_rpc import …`` imports keep working.
__all__ = [
    "DjangoQueueTransport",
    "PgExecutionDispatcher",
    "get_executor_dispatcher",
]


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

        row = poll_for_row(_fetch, timeout, between_polls=close_old_connections)
        if row is not None:
            # Reply consumed: clear the payload (result + error) so PII doesn't sit
            # in pg_task_result for the full retention TTL — mirrors the workers
            # transport's PgResultBackend.forget so both dispatch paths behave alike.
            # Best-effort: runs after the caller holds the result, inside
            # PgExecutionDispatcher.dispatch's never-raises guard, so a cleanup miss
            # must not fail a good RPC; the reaper's retention sweep is the backstop.
            try:
                PgTaskResult.objects.filter(pk=reply_key).update(result=None, error="")
            except Exception:
                logger.warning(
                    "DjangoQueueTransport: could not clear pg_task_result for "
                    "reply_key=%s after consume; the retention sweep will flush it",
                    reply_key,
                    exc_info=True,
                )
        return row


def get_executor_dispatcher() -> PgExecutionDispatcher:
    """Factory: the executor dispatcher.

    Takes no arguments. It used to accept a ``celery_app`` that fed the Celery
    branch of the routing dispatcher; that branch went with the ``pg_queue_enabled``
    flag (UN-4046), and the parameter was kept for a while so the call sites did not
    all need editing at once. Keeping an ignored parameter made the signature
    decoration rather than a contract — and it read as "this dispatcher may use
    Celery", which is exactly the belief that left a ``headers=`` argument at three
    call sites and broke every extraction. Removed.
    """
    return PgExecutionDispatcher(DjangoQueueTransport())
