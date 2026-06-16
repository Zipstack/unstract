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

import logging

from unstract.core.data_models import WorkflowTransport

logger = logging.getLogger(__name__)


def resolve_transport(
    workflow_id: str,
    pipeline_id: str | None = None,
    organization_id: str | None = None,
) -> str:
    """Resolve the transport for a new workflow execution.

    Args:
        workflow_id: The workflow being executed.
        pipeline_id: The pipeline, if this execution belongs to one.
        organization_id: The owning organization (for per-org rollout in PR 3).

    Returns:
        The transport value (a :class:`WorkflowTransport` value string).

    Note:
        PR 1 always returns ``"celery"``. The arguments are accepted now so the
        call sites and the contract are stable when PR 3 wires Flipt in here.
    """
    return WorkflowTransport.CELERY.value
