"""PG scheduler tick — the periodic-trigger half of the orchestrator (Phase 9, ②b).

Folded into the leader-elected reaper loop (the reaper becomes "the
orchestrator": recover + schedule, per the labs single-orchestrator model).
Each cycle, *only while leader*, it scans ``pg_periodic_schedule`` for rows it
owns (``pg_owned``) that are enabled and due, enqueues the existing
``scheduler.tasks.execute_pipeline_task`` onto the PG queue, and advances
``next_run_at`` — replacing what Celery Beat does, without Beat/RabbitMQ.

Correctness properties:

- **No re-fire on crash.** The enqueue and the ``next_run_at`` advance happen in
  **one transaction**, so a crash between them can't fire twice.
- **One firer per schedule (conditional).** A ``pg_owned`` row fires here; the
  no-double-fire guarantee with Beat depends on the matching Beat
  ``PeriodicTask`` being disabled when a schedule is handed over — that's the
  ②c ramp control, which does not exist yet. **Until it lands, safety rests on
  ``pg_owned`` defaulting to False** (nothing is owned → this fires nothing →
  Beat fires everything). A row manually flipped to ``pg_owned=True`` while its
  PeriodicTask is still enabled *would* double-fire.
- **No burst on hand-over.** A freshly-owned row has ``next_run_at IS NULL``; the
  first tick records its baseline next time and does **not** fire (matches Beat:
  a new schedule fires at its next cron match, not immediately).

Per-row isolation (mirrors :func:`recover_expired_barriers`): a bad cron or a DB
error on one row is rolled back, logged, and skipped without poisoning the
connection or blocking the other rows.
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, NamedTuple

from croniter import croniter

from unstract.core.data_models import TaskPayload

from ..fairness import DEFAULT_PRIORITY
from .client import INSERT_MESSAGE_SQL
from .task_payload import to_payload

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

# The fired task + the queue a `scheduler` PG consumer polls (QueueName.SCHEDULER).
PIPELINE_TRIGGER_TASK = "scheduler.tasks.execute_pipeline_task"
SCHEDULER_QUEUE_NAME = "scheduler"


class _DueSchedule(NamedTuple):
    """One row from the due-schedules scan — names bound to columns at one site
    so a future reorder of the SELECT can't silently misassign fields.
    """

    pipeline_id: uuid.UUID
    organization_id: str
    workflow_id: uuid.UUID | None
    pipeline_name: str
    cron_string: str
    next_run_at: datetime | None


def compute_next_run(cron_string: str, base: datetime) -> datetime:
    """Next fire time strictly after ``base`` for a 5-field cron expression."""
    return croniter(cron_string, base).get_next(datetime)


def _build_trigger_payload(
    *,
    workflow_id: str | uuid.UUID | None,
    organization_id: str,
    pipeline_id: str | uuid.UUID,
    pipeline_name: str,
) -> TaskPayload:
    """``execute_pipeline_task`` payload. Positional args match its signature:
    (workflow_id, org_schema, execution_action, execution_id, pipeline_id,
    with_logs, name). ``execution_action`` / ``execution_id`` are ignored by
    ``execute_pipeline_task_v2``, so we send blanks even though the Beat path
    populates ``execution_action`` (see SchedulerHelper._schedule_task_job).
    """
    return to_payload(
        PIPELINE_TRIGGER_TASK,
        args=[
            str(workflow_id) if workflow_id else "",
            organization_id or "",
            "",  # execution_action (ignored by v2)
            "",  # execution_id (ignored by v2)
            str(pipeline_id),
            False,  # with_logs (ignored by v2)
            pipeline_name or "",
        ],
        kwargs={},
        queue=SCHEDULER_QUEUE_NAME,
        fairness=None,
    )


def _quiesce_invalid_cron(conn: PgConnection, schedule: _DueSchedule) -> None:
    """Disable a row whose cron can't be parsed, so it stops being re-selected
    (and re-logging a traceback) every tick. Best-effort; logged once here.
    """
    logger.exception(
        "PG scheduler: invalid cron %r for pipeline %s — disabling the row",
        schedule.cron_string,
        schedule.pipeline_id,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pg_periodic_schedule SET enabled = FALSE WHERE pipeline_id = %s",
                (schedule.pipeline_id,),
            )
        conn.commit()
    except Exception:
        # If the disable UPDATE fails, roll back so the connection isn't left in
        # an aborted-transaction state that would poison the next row's INSERT.
        with contextlib.suppress(Exception):
            conn.rollback()


def dispatch_due_schedules(conn: PgConnection) -> int:
    """Fire PG-owned, enabled, due schedules; return the count actually fired.

    The caller (reaper tick) gates this on leadership. All time comparisons use
    the DB clock (``now()``). Each row is handled in its own transaction; a bad
    cron or a DB error on one row is rolled back + logged + skipped (the others
    still fire). The read step rolls back + re-raises on error so the connection
    is never handed back in an aborted-transaction state (mirrors
    :func:`recover_expired_barriers`).
    """
    try:
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
            due = [_DueSchedule(*row) for row in cur.fetchall()]
        conn.commit()
    except Exception:
        with contextlib.suppress(Exception):
            conn.rollback()
        raise

    fired = 0
    for schedule in due:
        try:
            nxt = compute_next_run(schedule.cron_string, base)
        except Exception:
            _quiesce_invalid_cron(conn, schedule)
            continue

        try:
            if schedule.next_run_at is None:
                # First observation of a freshly-owned row: record the baseline
                # next time and do NOT fire (no burst when handed over).
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE pg_periodic_schedule SET next_run_at = %s "
                        "WHERE pipeline_id = %s",
                        (nxt, schedule.pipeline_id),
                    )
                conn.commit()
                logger.info(
                    "PG scheduler: baselined pipeline %s (next_run_at=%s, not fired)",
                    schedule.pipeline_id,
                    nxt,
                )
                continue

            payload = _build_trigger_payload(
                workflow_id=schedule.workflow_id,
                organization_id=schedule.organization_id,
                pipeline_id=schedule.pipeline_id,
                pipeline_name=schedule.pipeline_name,
            )
            # Enqueue + advance in ONE transaction so a crash between them can't
            # re-fire next cycle. INSERT_MESSAGE_SQL is the shared enqueue
            # contract from client.py (send() uses the same constant).
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_MESSAGE_SQL,
                    (
                        SCHEDULER_QUEUE_NAME,
                        json.dumps(payload),
                        schedule.organization_id or "",
                        DEFAULT_PRIORITY,
                    ),
                )
                cur.execute(
                    "UPDATE pg_periodic_schedule "
                    "SET last_run_at = %s, next_run_at = %s WHERE pipeline_id = %s",
                    (base, nxt, schedule.pipeline_id),
                )
            conn.commit()
        except Exception:
            # A row-level failure (constraint, serialization, socket) must not
            # poison the connection or drop the rest of the batch — roll back +
            # leave the row for the next tick (next_run_at unchanged → re-fires).
            with contextlib.suppress(Exception):
                conn.rollback()
            logger.exception(
                "PG scheduler: failed to fire pipeline %s — leaving for next tick",
                schedule.pipeline_id,
            )
            continue

        fired += 1
        logger.info(
            "PG scheduler: fired pipeline %s → %s (next_run_at=%s)",
            schedule.pipeline_id,
            SCHEDULER_QUEUE_NAME,
            nxt,
        )

    return fired
