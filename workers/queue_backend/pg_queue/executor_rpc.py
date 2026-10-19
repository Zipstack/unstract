"""Executor-RPC for the PG path — workers (psycopg2) transport adapter.

The reply_key/timeout orchestration lives ONCE in
``unstract.workflow_execution.executor_rpc`` (shared with the backend). This module
is the thin psycopg2 half: a :class:`PgClientQueueTransport` that enqueues via
:class:`~queue_backend.pg_queue.client.PgQueueClient` and polls via
:class:`~queue_backend.pg_queue.result_backend.PgResultBackend`, plus the
:func:`get_executor_dispatcher` factory.

Since UN-4046 the factory returns the PG dispatcher unconditionally: there is no
gate, no routing dispatcher and no Celery fall-through, so a ``pg_task_result``
row is written on every request-reply dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from unstract.workflow_execution.executor_rpc import (
    EXECUTE_TASK,
    ExecResultRow,
    PgExecutionDispatcher,
    QueueTransport,
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
    "get_executor_dispatcher",
]


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
            if row is not None:
                # Reply consumed: drop the payload now so PII doesn't sit in
                # pg_task_result for the full retention TTL. Best-effort (see forget()).
                rb.forget(reply_key)
        if row is None:
            return None
        return ExecResultRow(
            status=row.get("status"), result=row.get("result"), error=row.get("error")
        )


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
    return PgExecutionDispatcher(PgClientQueueTransport())
