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

Routing onto PG needs **all three** of: the env master-gate on, Flipt reachable
(``FLIPT_SERVICE_AVAILABLE=true``), and the flag enabled for this execution.

- **Master-gate** (``settings.PG_QUEUE_TRANSPORT_ENABLED``, default off): until
  ops flips it on, Flipt is never consulted and every execution rides Celery.
  This is both the instant global kill-switch *and* the deploy-ordering safety —
  the flag stays inert until PG consumers are actually running in the fleet.
- **Flipt** decides per-execution: ``entity_id = execution_id`` drives the
  percentage-rollout hashing (an execution resolves exactly once, so it can
  never re-bucket mid-flight); ``context`` carries org/workflow/pipeline for
  segment rules. The flag contract is fixed in 9e-design §2.
- **Fail-closed to Celery**: a Flipt outage must never break execution creation,
  mirroring ``normalize_transport`` on the read side. The gate-ON path logs its
  decision so a "gate on but still all Celery" situation (e.g. a blind Flipt)
  is visible rather than silent.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from django.conf import settings

from unstract.core.data_models import WorkflowTransport
from unstract.flags.feature_flag import check_feature_flag_status

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)

# The fixed Flipt flag contract (9e-design §2): Boolean, default false.
PG_QUEUE_FLAG_KEY = "pg_queue_execution_enabled"


def resolve_transport(
    *,
    execution_id: str | UUID,
    organization_id: str | UUID,
    workflow_id: str | UUID | None = None,
    pipeline_id: str | UUID | None = None,
) -> str:
    """Resolve the transport for a new workflow execution.

    The id parameters are typed ``str | UUID`` because callers pass either
    (e.g. the view path pre-coerces with ``str(...)``, the helper path passes
    raw UUIDs). Coercion to the wire types Flipt needs is kept internal here so
    callers never have to know about it.

    Args:
        execution_id: The execution's id. Used as the Flipt ``entity_id`` so the
            percentage rollout buckets per execution and stays sticky (one
            execution is resolved exactly once).
        organization_id: The org's string identifier
            (``Organization.organization_id`` — the ``X-Organization-ID`` header
            value, *not* the DB pk). Carried in the Flipt ``context`` for per-org
            segment rollouts.
        workflow_id: Optional, carried in ``context`` for future segment rules.
        pipeline_id: Optional, carried in ``context`` for future segment rules.

    Returns:
        A :class:`WorkflowTransport` value string — ``"pg_queue"`` only when the
        master-gate is on, Flipt is reachable, and Flipt says yes for this
        execution; ``"celery"`` otherwise (including any error — fail-closed).
    """
    celery = WorkflowTransport.CELERY.value

    # Master-gate: until ops sets PG_QUEUE_TRANSPORT_ENABLED=true, never consult
    # Flipt — every execution rides Celery (kill-switch + deploy-ordering safety).
    # Intentionally unlogged: this is the steady state for every execution while
    # the gate is off, so a log here would be pure noise.
    if not settings.PG_QUEUE_TRANSPORT_ENABLED:
        return celery

    # Gate is ON (canary/rollout). From here the decision is logged so a
    # "gate on but everything still Celery" situation cannot hide.

    # No org context → per-org segment matching can't be trusted (str(None) would
    # ship a bogus "None" org into the Flipt context and mis-segment). The view
    # path validates the header non-None, but the helper path reads it from
    # StateStore, which can be empty. Fail closed rather than mis-bucket.
    if not organization_id:
        logger.warning(
            "resolve_transport: no organization_id for execution %s; forcing celery",
            execution_id,
        )
        return celery

    # FliptClient returns False for ALL flags when the service is marked
    # unavailable — indistinguishable from "rollout says no". Surface it loudly so
    # a blind Flipt under an ON gate doesn't masquerade as a healthy 100%-Celery
    # canary. (Mirrors FliptClient's own FLIPT_SERVICE_AVAILABLE env read.)
    if os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").strip().lower() != "true":
        logger.warning(
            "resolve_transport: gate ON but FLIPT_SERVICE_AVAILABLE != true "
            "(Flipt is blind) for execution %s; forcing celery",
            execution_id,
        )
        return celery

    # Flipt's context is a gRPC map<string,string>; callers pass UUID objects for
    # the ids, so coerce every value to str. A non-str value makes the client's
    # serialization fail and check_feature_flag_status swallow it as False —
    # silently forcing celery. entity_id is str-coerced for the same reason (and
    # so the %-rollout hash is stable across str/UUID call sites).
    context = {"organization_id": str(organization_id)}
    if workflow_id:
        context["workflow_id"] = str(workflow_id)
    if pipeline_id:
        context["pipeline_id"] = str(pipeline_id)

    # Defense in depth: check_feature_flag_status already wraps its body in
    # try/except → False, but an explicit fail-closed wrap here keeps a future
    # change to that helper from ever letting a Flipt problem break execution
    # creation.
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

    result = WorkflowTransport.PG_QUEUE.value if enabled else celery
    logger.info(
        "resolve_transport: execution %s resolved to %s (flipt enabled=%s)",
        execution_id,
        result,
        enabled,
    )
    return result
