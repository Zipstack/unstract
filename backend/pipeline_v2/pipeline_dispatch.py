"""Transport-routed dispatch for the API-triggered pipeline execution trigger.

The **scheduled** pipeline path already enqueues
``scheduler.tasks.execute_pipeline_task`` onto the PG queue
(``pg_scheduler.dispatch_due_schedules`` → the ``scheduler`` queue, run by
``worker-pg-scheduler``). The **API-trigger** view historically sent it only to
Celery — so when the flag was on, the trigger stayed on Celery while the
execution it spawns rode PG, breaking uniform flag control. This routes the
trigger through the same :func:`resolve_transport` flag as everything else.

**Fail-closed / zero regression:** with the master gate off (production default)
``resolve_transport`` returns Celery → identical to the prior ``send_task``. The
task args are byte-identical on both paths, so the consumer behaves the same
regardless of transport.
"""

from __future__ import annotations

import logging
from typing import Any

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
    org_id: str,
    pipeline_id: str,
    pipeline_name: str,
) -> str:
    """Dispatch the pipeline-trigger task on the resolved transport.

    Returns the transport actually used (``"pg_queue"`` / ``"celery"``). The
    positional args match ``execute_pipeline_task``'s signature on **both** paths:
    ``(workflow_id, org_schema, execution_action, execution_id, pipeline_id,
    with_logs, name)``.
    """
    args = ["", org_id, "", "", str(pipeline_id), True, pipeline_name]
    # No execution exists yet (it's created inside the task), so the trigger
    # buckets the flag by pipeline_id as the sticky entity.
    transport = resolve_transport(
        execution_id=pipeline_id,
        organization_id=org_id,
        pipeline_id=pipeline_id,
    )
    if transport == WorkflowTransport.PG_QUEUE.value:
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
        return transport
    celery_app.send_task(PIPELINE_TRIGGER_TASK, args=args)
    logger.info("Pipeline %s trigger dispatched on Celery", pipeline_id)
    return transport
