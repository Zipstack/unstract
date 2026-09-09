"""PG scheduler tick — the periodic-trigger half of the orchestrator.

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
  ramp control, which does not exist yet. **Until it lands, safety rests on
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
from .client import insert_message_sql
from .schema import qualified
from .task_payload import to_payload

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

# The fired task + the queue a `scheduler` PG consumer polls (QueueName.SCHEDULER).
PIPELINE_TRIGGER_TASK = "scheduler.tasks.execute_pipeline_task"
SCHEDULER_QUEUE_NAME = "scheduler"


class _DueSchedule(NamedTuple):
    """One row from the due-schedules scan.

    THE FIELD NAMES ARE THE QUERY. They are emitted verbatim as the SELECT's column
    list (see the scan below), so every one MUST be a column of
    ``pg_periodic_schedule`` — renaming a field here rewrites the SQL and needs a
    matching migration in ``backend/pg_queue/models.py``. That is what makes a reorder
    harmless (there is no second list to drift from) and a RENAME dangerous, which is
    the opposite of what an earlier version of this docstring implied.
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
                f"UPDATE {qualified('pg_periodic_schedule')} "
                "SET enabled = FALSE WHERE pipeline_id = %s",
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
                f"""
                SELECT {", ".join(f'"{f}"' for f in _DueSchedule._fields)}
                FROM {qualified("pg_periodic_schedule")}
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
                        f"UPDATE {qualified('pg_periodic_schedule')} "
                        "SET next_run_at = %s WHERE pipeline_id = %s",
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
            # re-fire next cycle. insert_message_sql() is the shared enqueue
            # contract from client.py (send() uses the same helper).
            with conn.cursor() as cur:
                cur.execute(
                    insert_message_sql(),
                    (
                        SCHEDULER_QUEUE_NAME,
                        json.dumps(payload),
                        schedule.organization_id or "",
                        DEFAULT_PRIORITY,
                    ),
                )
                cur.execute(
                    f"UPDATE {qualified('pg_periodic_schedule')} "
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


class _DuePeriodicTask(NamedTuple):
    """One row from the generic-periodic due scan (UN-3796).

    Sibling of :class:`_DueSchedule`, and carries the same rule: the field names are
    emitted verbatim as the SELECT's column list, so each MUST be a column of
    ``pg_periodic_task``.

    Note this type says ``org_id`` where its sibling says ``organization_id``. Tempting
    to unify — do not, without a migration. The two back different tables, and renaming
    this one would silently select a column ``pg_periodic_task`` does not have; the
    resulting UndefinedColumn propagates out of the dispatch and takes down the whole
    leader tick, retention sweep and gauge refresh included.
    """

    name: str
    task_name: str
    queue: str
    task_args: list
    task_kwargs: dict
    org_id: str
    cron_string: str
    next_run_at: datetime | None


def _quiesce_invalid_periodic_cron(conn: PgConnection, row: _DuePeriodicTask) -> None:
    """Disable a generic periodic whose cron won't parse, so it stops being
    re-selected (and re-logging a traceback) every tick. Mirrors
    :func:`_quiesce_invalid_cron` for the pipeline table.
    """
    logger.exception(
        "PG scheduler: invalid cron %r for periodic %r — disabling the row",
        row.cron_string,
        row.name,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE {qualified('pg_periodic_task')} "
                "SET enabled = FALSE WHERE name = %s",
                (row.name,),
            )
        conn.commit()
    except Exception:
        with contextlib.suppress(Exception):
            conn.rollback()


def dispatch_due_periodic_tasks(conn: PgConnection) -> int:
    """Fire PG-owned, enabled, due **non-pipeline** periodics; return the count fired.

    The Beat-replacement half for everything that isn't a pipeline trigger
    (UN-3796): ``dashboard_metrics.*``, log-history, audit, and anything an operator
    adds. Structurally identical to :func:`dispatch_due_schedules` — leader-gated by
    the caller, DB clock throughout, per-row transaction, enqueue and ``next_run_at``
    advance in ONE transaction so a crash between them cannot double-fire, first
    observation of a freshly-owned row records a baseline without firing.

    The one real difference: each row carries its **own** target queue and its own
    task/args/kwargs, where the pipeline dispatcher rebuilds one fixed argument list
    onto one fixed queue. That is the whole reason for the second table.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT now()")
            base = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT {", ".join(f'"{f}"' for f in _DuePeriodicTask._fields)}
                FROM {qualified("pg_periodic_task")}
                WHERE pg_owned AND enabled
                  AND (next_run_at IS NULL OR next_run_at <= %s)
                """,
                (base,),
            )
            due = [_DuePeriodicTask(*row) for row in cur.fetchall()]
        conn.commit()
    except Exception:
        with contextlib.suppress(Exception):
            conn.rollback()
        raise

    fired = 0
    for row in due:
        try:
            nxt = compute_next_run(row.cron_string, base)
        except Exception:
            _quiesce_invalid_periodic_cron(conn, row)
            continue

        try:
            if row.next_run_at is None:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {qualified('pg_periodic_task')} "
                        "SET next_run_at = %s WHERE name = %s",
                        (nxt, row.name),
                    )
                conn.commit()
                logger.info(
                    "PG scheduler: baselined periodic %r (next_run_at=%s, not fired)",
                    row.name,
                    nxt,
                )
                continue

            payload = to_payload(
                row.task_name,
                args=list(row.task_args or []),
                kwargs=dict(row.task_kwargs or {}),
                queue=row.queue,
                fairness=None,
            )
            # Enqueue + advance in ONE transaction (see the module docstring).
            with conn.cursor() as cur:
                cur.execute(
                    insert_message_sql(),
                    (
                        row.queue,
                        json.dumps(payload),
                        row.org_id or "",
                        DEFAULT_PRIORITY,
                    ),
                )
                cur.execute(
                    f"UPDATE {qualified('pg_periodic_task')} "
                    "SET last_run_at = %s, next_run_at = %s WHERE name = %s",
                    (base, nxt, row.name),
                )
            conn.commit()
        except Exception:
            with contextlib.suppress(Exception):
                conn.rollback()
            logger.exception(
                "PG scheduler: failed to fire periodic %r — leaving for next tick",
                row.name,
            )
            continue

        fired += 1
        logger.info(
            "PG scheduler: fired periodic %r (%s) → %s (next_run_at=%s)",
            row.name,
            row.task_name,
            row.queue,
            nxt,
        )

    return fired
