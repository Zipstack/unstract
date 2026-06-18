"""PG scheduler tick — the periodic-trigger half of the orchestrator (Phase 9, ②b).

Folded into the leader-elected reaper loop (the reaper becomes "the
orchestrator": recover + schedule, per the labs single-orchestrator model).
Each cycle, *only while leader*, it scans ``pg_periodic_schedule`` for rows it
owns (``pg_owned``) that are enabled and due, enqueues the existing
``scheduler.tasks.execute_pipeline_task`` onto the PG queue, and advances
``next_run_at`` — replacing what Celery Beat does, without Beat/RabbitMQ.

Two correctness properties:

- **Never double-fires.** A row fires from exactly one side: ``pg_owned`` rows
  fire here and have their Beat ``PeriodicTask`` disabled (by the ramp control,
  next slice); non-owned rows fire from Beat. The enqueue and the ``next_run_at``
  advance happen in **one transaction**, so a crash between them can't re-fire.
- **No burst on hand-over.** A freshly-owned row has ``next_run_at IS NULL``; the
  first tick records its baseline next time and does **not** fire (matches Beat:
  a new schedule fires at its next cron match, not immediately).

**Dark by default:** rows are ``pg_owned=False`` until explicitly handed over, so
a fresh deploy fires nothing — the reaper does recovery-only as today.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from croniter import croniter

from ..fairness import DEFAULT_PRIORITY
from .task_payload import to_payload

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

# The fired task + the queue a `scheduler` PG consumer polls (QueueName.SCHEDULER).
PIPELINE_TRIGGER_TASK = "scheduler.tasks.execute_pipeline_task"
SCHEDULER_QUEUE_NAME = "scheduler"


def compute_next_run(cron_string: str, base: datetime) -> datetime:
    """Next fire time strictly after ``base`` for a 5-field cron expression."""
    return croniter(cron_string, base).get_next(datetime)


def _build_trigger_payload(
    *,
    workflow_id: object,
    organization_id: str,
    pipeline_id: object,
    pipeline_name: str,
) -> dict:
    """``execute_pipeline_task`` payload. Positional args match its signature:
    (workflow_id, org_schema, execution_action, execution_id, pipeline_id,
    with_logs, name) — the middle two are unused legacy args kept for
    compatibility (see SchedulerHelper._schedule_task_job).
    """
    return to_payload(
        PIPELINE_TRIGGER_TASK,
        args=[
            str(workflow_id) if workflow_id else "",
            organization_id or "",
            "",  # execution_action (unused)
            "",  # execution_id (unused legacy arg)
            str(pipeline_id),
            False,  # with_logs (unused)
            pipeline_name or "",
        ],
        kwargs={},
        queue=SCHEDULER_QUEUE_NAME,
        fairness=None,
    )


def dispatch_due_schedules(conn: PgConnection) -> int:
    """Fire PG-owned, enabled, due schedules; return the count actually fired.

    The caller (reaper tick) gates this on leadership. All time comparisons use
    the DB clock (``now()``), matching the leader-election's clock-safety posture.
    Each row is handled in its own transaction; a baseline-only row just records
    its ``next_run_at``, a due row enqueues + advances atomically. A bad cron on
    one row is logged and skipped without blocking the others.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT now()")
        base = cur.fetchone()[0]
        cur.execute(
            """
            SELECT pipeline_id, organization_id, workflow_id, pipeline_name,
                   cron_string, next_run_at
            FROM pg_periodic_schedule
            WHERE pg_owned AND enabled
              AND (next_run_at IS NULL OR next_run_at <= %s)
            """,
            (base,),
        )
        due = cur.fetchall()
    conn.commit()  # release the read snapshot; per-row work commits on its own

    fired = 0
    for (
        pipeline_id,
        organization_id,
        workflow_id,
        pipeline_name,
        cron_string,
        next_run_at,
    ) in due:
        try:
            nxt = compute_next_run(cron_string, base)
        except Exception:
            logger.exception(
                "PG scheduler: invalid cron %r for pipeline %s — skipping",
                cron_string,
                pipeline_id,
            )
            continue

        if next_run_at is None:
            # First observation of a freshly-owned row: record the baseline next
            # time and do NOT fire (no burst when a schedule is handed over).
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pg_periodic_schedule SET next_run_at = %s "
                    "WHERE pipeline_id = %s",
                    (nxt, pipeline_id),
                )
            conn.commit()
            logger.info(
                "PG scheduler: baselined pipeline %s (next_run_at=%s, not fired)",
                pipeline_id,
                nxt,
            )
            continue

        payload = _build_trigger_payload(
            workflow_id=workflow_id,
            organization_id=organization_id,
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
        )
        with conn.cursor() as cur:
            # Enqueue + advance in ONE transaction so a crash between them can't
            # re-fire next cycle. The INSERT mirrors PgQueueClient.send (the
            # canonical shape) — inlined here only to share this transaction.
            cur.execute(
                "INSERT INTO pg_queue_message "
                "(queue_name, message, org_id, priority, enqueued_at, vt, read_ct) "
                "VALUES (%s, %s::jsonb, %s, %s, now(), now(), 0)",
                (
                    SCHEDULER_QUEUE_NAME,
                    json.dumps(payload),
                    organization_id or "",
                    DEFAULT_PRIORITY,
                ),
            )
            cur.execute(
                "UPDATE pg_periodic_schedule "
                "SET last_run_at = %s, next_run_at = %s WHERE pipeline_id = %s",
                (base, nxt, pipeline_id),
            )
        conn.commit()
        fired += 1
        logger.info(
            "PG scheduler: fired pipeline %s → %s (next_run_at=%s)",
            pipeline_id,
            SCHEDULER_QUEUE_NAME,
            nxt,
        )

    return fired
