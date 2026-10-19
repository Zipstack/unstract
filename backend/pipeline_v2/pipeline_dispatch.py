"""PG-queue dispatch for the API-triggered pipeline execution trigger.

Enqueues ``scheduler.tasks.execute_pipeline_task`` onto the PG ``scheduler``
queue, where ``worker-pg-scheduler`` polls it — the same queue and task the
scheduled-pipeline path uses (``pg_scheduler.dispatch_due_schedules``), so the
API trigger and the schedule trigger are at parity.

This used to route through ``resolve_transport``/``pg_queue_enabled`` and fall
back to ``celery_app.send_task``. The flag is gone (UN-4046) and PG is the only
transport, so the Celery branch went with it.

``args`` are JSON-normalized by ``enqueue_task`` (UUIDs/datetimes → str), a no-op
for these string/bool values.
"""

from __future__ import annotations

import logging
from uuid import UUID

from pg_queue.producer import enqueue_task

logger = logging.getLogger(__name__)

# The fired task + the PG queue a ``scheduler`` consumer polls. Mirrors
# ``pg_scheduler.PIPELINE_TRIGGER_TASK`` / ``SCHEDULER_QUEUE_NAME`` — kept as local
# constants so the backend doesn't import the workers package.
PIPELINE_TRIGGER_TASK = "scheduler.tasks.execute_pipeline_task"
SCHEDULER_QUEUE = "scheduler"


def dispatch_pipeline_trigger(
    *,
    org_id: str | UUID,
    pipeline_id: str | UUID,
    pipeline_name: str,
) -> None:
    """Enqueue the pipeline-trigger task on the PG scheduler queue.

    The positional args match ``execute_pipeline_task``'s signature:
    ``(workflow_id, org_schema, execution_action, execution_id, pipeline_id,
    with_logs, name)``. ``org_id`` / ``pipeline_id`` accept ``UUID`` and are
    str-coerced into the task args.
    """
    args = ["", str(org_id), "", "", str(pipeline_id), True, pipeline_name]
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
