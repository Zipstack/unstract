"""Transport resolution for a workflow execution (9e).

A workflow execution rides one transport end-to-end — legacy Celery/RabbitMQ
or the bespoke Postgres queue. The choice is resolved **once**, at the
execution-creation chokepoint, and returned to the caller so it can be carried
in the dispatched task's payload (see ``workers/queue_backend/pg_queue/
9e-design.md``). It is deliberately **not** persisted on the ``WorkflowExecution``
row: the payload is the single carrier, durable for PG via the queue row's
JSONB, and the giant shared table is never migrated for this work.

PR 3 (this change) replaces PR 1's hardwired Celery with a Flipt evaluation:

  master-gate (env) → Flipt boolean (``pg_queue_execution_enabled``) → transport

- **Master-gate** (``settings.PG_QUEUE_TRANSPORT_ENABLED``, default off): until
  ops flips it on, Flipt is never consulted and every execution rides Celery.
  This is both the instant global kill-switch *and* the deploy-ordering safety —
  the flag stays inert until PG consumers are actually running in the fleet.
- **Flipt** decides per-execution: ``entity_id = execution_id`` drives the
  percentage-rollout hashing (an execution resolves exactly once, so it can
  never re-bucket mid-flight); ``context`` carries org/workflow/pipeline for
  segment rules. The flag contract is fixed in 9e-design §2.
- **Fail-closed to Celery**: a Flipt outage must never break execution creation,
  mirroring ``normalize_transport`` on the read side.
"""

from __future__ import annotations

import logging

from django.conf import settings

from unstract.core.data_models import WorkflowTransport
from unstract.flags.feature_flag import check_feature_flag_status

logger = logging.getLogger(__name__)

# The fixed Flipt flag contract (9e-design §2): Boolean, default false.
PG_QUEUE_FLAG_KEY = "pg_queue_execution_enabled"


def resolve_transport(
    *,
    execution_id: str,
    organization_id: str,
    workflow_id: str | None = None,
    pipeline_id: str | None = None,
) -> str:
    """Resolve the transport for a new workflow execution.

    Args:
        execution_id: The execution's id. Used as the Flipt ``entity_id`` so the
            percentage rollout buckets per execution and stays sticky (one
            execution is resolved exactly once).
        organization_id: Owning org's public identifier. Carried in the Flipt
            ``context`` for per-org segment rollouts.
        workflow_id: Optional, carried in ``context`` for future segment rules.
        pipeline_id: Optional, carried in ``context`` for future segment rules.

    Returns:
        A :class:`WorkflowTransport` value string — ``"pg_queue"`` only when the
        master-gate is on *and* Flipt says yes for this execution; ``"celery"``
        otherwise (including any Flipt error — fail-closed).
    """
    celery = WorkflowTransport.CELERY.value

    # Master-gate: until ops sets PG_QUEUE_TRANSPORT_ENABLED=true, never consult
    # Flipt — every execution rides Celery (kill-switch + deploy-ordering safety).
    if not settings.PG_QUEUE_TRANSPORT_ENABLED:
        return celery

    # Flipt's context is a gRPC map<string,string>; callers pass UUID objects
    # for the ids, so coerce every value to str. A non-str value makes the
    # client's serialization fail and check_feature_flag_status swallow it as
    # False — silently forcing celery. entity_id is str-coerced for the same
    # reason (and so the %-rollout hash is stable across str/UUID call sites).
    context = {"organization_id": str(organization_id)}
    if workflow_id:
        context["workflow_id"] = str(workflow_id)
    if pipeline_id:
        context["pipeline_id"] = str(pipeline_id)

    # Defense in depth: check_feature_flag_status already swallows errors and
    # returns False, but the design mandates an explicit fail-closed wrap here so
    # a future change to that helper (or an import-time fault) can never let a
    # Flipt problem break execution creation.
    try:
        enabled = check_feature_flag_status(
            flag_key=PG_QUEUE_FLAG_KEY,
            entity_id=str(execution_id),
            context=context,
        )
    except Exception:
        logger.warning(
            "resolve_transport: Flipt evaluation failed for execution %s; "
            "falling back to Celery",
            execution_id,
            exc_info=True,
        )
        return celery

    return WorkflowTransport.PG_QUEUE.value if enabled else celery
