"""Transport resolution for a workflow execution (9e).

A workflow execution rides one transport end-to-end — legacy Celery/RabbitMQ
or the bespoke Postgres queue. The choice is resolved **once**, at the
execution-creation chokepoint, and returned to the caller so it can be carried
in the dispatched task's payload (see ``workers/queue_backend/pg_queue/
9e-design.md``). It is deliberately **not** persisted on the ``WorkflowExecution``
row: the payload is the single carrier, durable for PG via the queue row's
JSONB, and the giant shared table is never migrated for this work.

PR 1 (this seam) hardwires the result to Celery, so behaviour is byte-identical
to today. PR 3 replaces the body with a Flipt evaluation (percentage rollout via
``entity_id`` hashing + per-org segment via ``context``), wrapped by an env
kill-switch and failing closed to Celery.
"""

from __future__ import annotations

from unstract.core.data_models import WorkflowTransport


def resolve_transport() -> str:
    """Resolve the transport for a new workflow execution.

    Returns:
        The transport value (a :class:`WorkflowTransport` value string).

    Note:
        PR 1 always returns ``"celery"`` and takes no arguments (the inert seam
        needs no inputs). PR 3 reintroduces ``workflow_id`` / ``pipeline_id`` /
        ``organization_id`` parameters when it wires Flipt here — percentage
        rollout via ``entity_id`` hashing + per-org segment via ``context`` —
        and updates the two call sites (``internal_api_views`` view and
        ``workflow_helper.execute_workflow_async``). PR 3 must wrap the Flipt
        evaluation in ``try/except`` and fall back to
        ``WorkflowTransport.CELERY.value`` (fail-closed), so a Flipt outage can
        never break execution creation — mirroring ``normalize_transport`` on
        the read side.
    """
    return WorkflowTransport.CELERY.value
