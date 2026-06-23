"""Transport-routed dispatch for the API-triggered pipeline execution trigger.

Routes ``scheduler.tasks.execute_pipeline_task`` through the same
:func:`resolve_transport` flag as the rest of the execution path: the PG queue
when enabled for this pipeline/org, else Celery. **Fail-closed** — with the
master gate off (the production default) it resolves to Celery, behaving exactly
like the prior unconditional ``send_task`` (zero regression). The
scheduled-pipeline path already enqueues this task onto the PG ``scheduler``
queue (``pg_scheduler.dispatch_due_schedules``, run by ``worker-pg-scheduler``);
this brings the API-trigger view to parity.

The same ``args`` are sent on both paths; on PG they're JSON-normalized by
``enqueue_task`` (UUIDs/datetimes → str), a no-op for these string/bool values,
so the consumer sees the same payload.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from pg_queue.producer import enqueue_task
from workflow_manager.workflow_v2.transport import resolve_transport

from unstract.core.data_models import WorkflowTransport

logger = logging.getLogger(__name__)

# The fired task + the PG queue a ``scheduler`` consumer polls. Mirrors
# ``pg_scheduler.PIPELINE_TRIGGER_TASK`` / ``SCHEDULER_QUEUE_NAME`` — kept as local
# constants so the backend doesn't import the workers package.
PIPELINE_TRIGGER_TASK = "scheduler.tasks.execute_pipeline_task"
SCHEDULER_QUEUE = "scheduler"


def dispatch_pipeline_trigger(
    *,
    celery_app: Any,
    org_id: str | UUID,
    pipeline_id: str | UUID,
    pipeline_name: str,
) -> None:
    """Dispatch the pipeline-trigger task on the resolved transport.

    The positional args match ``execute_pipeline_task``'s signature on **both**
    paths: ``(workflow_id, org_schema, execution_action, execution_id,
    pipeline_id, with_logs, name)``. ``org_id`` / ``pipeline_id`` accept ``UUID``
    (what ``resolve_transport`` takes) and are str-coerced into the task args.
    """
    args = ["", str(org_id), "", "", str(pipeline_id), True, pipeline_name]
    # No execution exists yet (it's created inside the task), so the trigger
    # buckets the flag by pipeline_id as the sticky entity.
    transport = resolve_transport(
        execution_id=pipeline_id,
        organization_id=org_id,
        pipeline_id=pipeline_id,
    )
    # Compare the enum member (not a bare string) so a literal typo can't silently
    # fall through to the Celery branch; WorkflowTransport is a str-enum.
    if transport == WorkflowTransport.PG_QUEUE:
        msg_id = enqueue_task(
            task_name=PIPELINE_TRIGGER_TASK,
            queue=SCHEDULER_QUEUE,
            args=args,
            org_id=str(org_id or ""),
        )
        logger.info(
            "Pipeline %s trigger enqueued on PG scheduler queue (msg_id=%s)",
            pipeline_id,
            msg_id,
        )
    else:
        celery_app.send_task(PIPELINE_TRIGGER_TASK, args=args)
        logger.info("Pipeline %s trigger dispatched on Celery", pipeline_id)
