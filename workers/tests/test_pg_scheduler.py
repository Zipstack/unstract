"""Tests for the PG scheduler tick (Phase 9, ②b).

Pure tests (cron next-run, payload shape) need no DB. The dispatch behaviour is
exercised against real Postgres via the shared ``pg_conn`` fixture (skips when
unreachable/unmigrated). ``dispatch_due_schedules`` commits, so the real-PG
tests seed + clean up their own rows under a unique org marker.
"""

import datetime
import json
import uuid

import psycopg2
import pytest

from queue_backend.pg_queue.pg_scheduler import (
    SCHEDULER_QUEUE_NAME,
    _build_trigger_payload,
    compute_next_run,
    dispatch_due_periodic_tasks,
    dispatch_due_schedules,
)


class TestPureHelpers:
    def test_the_field_names_ARE_the_select_column_lists(self):
        """The one guarantee the _fields-derived SELECT cannot give itself.

        Deriving the column list from the type makes a REORDER harmless — there is no
        second list to drift from. It makes a RENAME silent in a new way: the query
        simply starts asking for a different column. Every test that would execute
        these queries needs live Postgres and SKIPS without it, so a rename would
        otherwise reach production unchallenged.

        Pinning the tuples turns that into a red test in the default lane, which forces
        whoever renames a field to confirm a matching migration in
        backend/pg_queue/models.py. Do NOT update these literals to match a rename
        without doing so — that is the mistake this exists to stop.
        """
        from queue_backend.pg_queue.pg_scheduler import _DuePeriodicTask, _DueSchedule

        assert _DueSchedule._fields == (
            "pipeline_id",
            "organization_id",
            "workflow_id",
            "pipeline_name",
            "cron_string",
            "next_run_at",
        )
        assert _DuePeriodicTask._fields == (
            "name",
            "task_name",
            "queue",
            "task_args",
            "task_kwargs",
            "org_id",
            "cron_string",
            "next_run_at",
        )

    def test_next_run_is_strictly_after_base(self):
        base = datetime.datetime(2026, 6, 18, 10, 0, 0)
        # 09:00 daily — already past at 10:00, so the next is tomorrow 09:00.
        assert compute_next_run("0 9 * * *", base) == datetime.datetime(
            2026, 6, 19, 9, 0, 0
        )

    def test_next_run_same_day_when_upcoming(self):
        base = datetime.datetime(2026, 6, 18, 8, 0, 0)
        assert compute_next_run("0 9 * * *", base) == datetime.datetime(
            2026, 6, 18, 9, 0, 0
        )

    def test_next_run_preserves_tzaware_base(self):
        # Production base is tz-aware (SELECT now()); the result must be aware too.
        base = datetime.datetime(2026, 6, 18, 10, 0, 0, tzinfo=datetime.timezone.utc)
        nxt = compute_next_run("0 9 * * *", base)
        assert nxt.tzinfo is not None
        assert nxt == datetime.datetime(
            2026, 6, 19, 9, 0, 0, tzinfo=datetime.timezone.utc
        )

    def test_invalid_cron_raises(self):
        base = datetime.datetime(2026, 6, 18, 10, 0, 0)
        with pytest.raises(ValueError):
            compute_next_run("not a cron", base)

    def test_trigger_payload_shape(self):
        p = _build_trigger_payload(
            workflow_id="wf-1",
            organization_id="org-1",
            pipeline_id="pid-1",
            pipeline_name="Nightly ETL",
        )
        assert p["task_name"] == "scheduler.tasks.execute_pipeline_task"
        assert p["queue"] == SCHEDULER_QUEUE_NAME
        # (workflow_id, org, execution_action, execution_id, pipeline_id, with_logs, name)
        assert p["args"] == ["wf-1", "org-1", "", "", "pid-1", False, "Nightly ETL"]
        assert p["kwargs"] == {}
        assert p["fairness"] is None


# --- real-PG dispatch behaviour ---

_MARKER = f"test_pgsched_{uuid.uuid4().hex[:8]}"


def _seed(conn, *, pg_owned, enabled, next_run_at, cron="0 9 * * *"):
    """Insert one pg_periodic_schedule row; returns its pipeline_id (str)."""
    pid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pg_periodic_schedule
              (pipeline_id, organization_id, workflow_id, pipeline_name,
               cron_string, enabled, pg_owned, last_run_at, next_run_at,
               created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, now(), now())
            """,
            (
                pid,
                _MARKER,
                str(uuid.uuid4()),
                "Test ETL",
                cron,
                enabled,
                pg_owned,
                next_run_at,
            ),
        )
    conn.commit()
    return pid


def _row(conn, pid):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_run_at, next_run_at FROM pg_periodic_schedule "
            "WHERE pipeline_id = %s",
            (pid,),
        )
        return cur.fetchone()


def _queued_messages(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT message FROM pg_queue_message WHERE queue_name = %s AND org_id = %s",
            (SCHEDULER_QUEUE_NAME, _MARKER),
        )
        return [r[0] for r in cur.fetchall()]


@pytest.fixture
def clean(pg_conn):
    """Remove any rows this test created (the tick commits, so teardown must)."""
    yield pg_conn
    with pg_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM pg_periodic_schedule WHERE organization_id = %s", (_MARKER,)
        )
        cur.execute("DELETE FROM pg_queue_message WHERE org_id = %s", (_MARKER,))
    pg_conn.commit()


class TestDispatchDueSchedules:
    def test_due_owned_row_fires_and_advances(self, clean):
        conn = clean
        past = datetime.datetime(2020, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        pid = _seed(conn, pg_owned=True, enabled=True, next_run_at=past)

        fired = dispatch_due_schedules(conn)

        assert fired == 1  # fired exactly once (not zero, not double)
        msgs = _queued_messages(conn)
        assert len(msgs) == 1
        payload = msgs[0]
        assert payload["task_name"] == "scheduler.tasks.execute_pipeline_task"
        assert payload["args"][4] == pid  # pipeline_id at index 4
        last_run, next_run = _row(conn, pid)
        assert last_run is not None  # fired → last_run stamped
        # Advanced to the cron's next match (09:00 UTC), not just "something > past".
        assert (next_run.hour, next_run.minute, next_run.second) == (9, 0, 0)
        assert next_run > last_run

    def test_null_next_run_baselines_without_firing(self, clean):
        conn = clean
        pid = _seed(conn, pg_owned=True, enabled=True, next_run_at=None)

        assert dispatch_due_schedules(conn) == 0  # baseline is NOT a fire
        assert _queued_messages(conn) == []
        last_run, next_run = _row(conn, pid)
        assert last_run is None  # never fired
        assert next_run is not None  # baseline recorded

    def test_two_due_rows_both_fire(self, clean):
        conn = clean
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        p1 = _seed(conn, pg_owned=True, enabled=True, next_run_at=past)
        p2 = _seed(conn, pg_owned=True, enabled=True, next_run_at=past)

        assert dispatch_due_schedules(conn) == 2
        fired_pids = {m["args"][4] for m in _queued_messages(conn)}
        assert fired_pids == {p1, p2}

    def test_not_owned_row_is_skipped(self, clean):
        conn = clean
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        _seed(conn, pg_owned=False, enabled=True, next_run_at=past)

        dispatch_due_schedules(conn)

        assert _queued_messages(conn) == []

    def test_disabled_row_is_skipped(self, clean):
        conn = clean
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        _seed(conn, pg_owned=True, enabled=False, next_run_at=past)

        dispatch_due_schedules(conn)

        assert _queued_messages(conn) == []

    def test_future_next_run_not_yet_due(self, clean):
        conn = clean
        future = datetime.datetime(2099, 1, 1, tzinfo=datetime.timezone.utc)
        _seed(conn, pg_owned=True, enabled=True, next_run_at=future)

        dispatch_due_schedules(conn)

        assert _queued_messages(conn) == []

    def test_bad_cron_skipped_and_disabled(self, clean):
        conn = clean
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        bad = _seed(conn, pg_owned=True, enabled=True, next_run_at=past, cron="garbage")
        good = _seed(conn, pg_owned=True, enabled=True, next_run_at=past)

        dispatch_due_schedules(conn)

        msgs = _queued_messages(conn)
        # Only the good row fired; the bad-cron row was skipped, not fatal.
        assert len(msgs) == 1
        assert msgs[0]["args"][4] == good
        # The bad-cron row is disabled so it stops being re-selected every tick.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT enabled FROM pg_periodic_schedule WHERE pipeline_id = %s",
                (bad,),
            )
            assert cur.fetchone()[0] is False

    def test_advance_failure_rolls_back_the_enqueue(self, clean):
        """Atomicity: if the next_run_at advance fails after the INSERT, the
        INSERT must roll back with it — no orphan message, next_run unchanged
        (so the row simply re-fires next tick rather than double-firing)."""
        conn = clean
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        pid = _seed(conn, pg_owned=True, enabled=True, next_run_at=past)

        # The per-row failure is swallowed (isolation), so dispatch returns 0.
        # Fail the fire-path advance (the only UPDATE setting last_run_at).
        proxy = _FailingConn(conn, lambda sql: "last_run_at" in sql)
        fired = dispatch_due_schedules(proxy)

        assert fired == 0
        assert _queued_messages(conn) == []  # INSERT rolled back with the UPDATE
        last_run, next_run = _row(conn, pid)
        assert last_run is None  # not advanced
        assert next_run == past  # unchanged → re-fires next tick (no double-fire)

    def test_quiesce_failure_does_not_poison_next_row(self, clean):
        """If disabling a bad-cron row fails, the rollback must leave the conn
        clean so a following healthy row still fires (greptile P1)."""
        conn = clean
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        _seed(conn, pg_owned=True, enabled=True, next_run_at=past, cron="garbage")
        good = _seed(conn, pg_owned=True, enabled=True, next_run_at=past)

        # Make the bad-cron disable UPDATE fail; the good row must still fire.
        proxy = _FailingConn(conn, lambda sql: "enabled = FALSE" in sql)
        dispatch_due_schedules(proxy)

        msgs = _queued_messages(conn)
        assert len(msgs) == 1
        assert msgs[0]["args"][4] == good


class _FailingConn:
    """Wraps a real connection so an ``execute`` whose SQL matches ``fail_when``
    raises — to prove a statement failure rolls back cleanly. Everything else
    (commit/rollback/other statements) passes through to the real connection.
    """

    def __init__(self, real, fail_when):
        self._real = real
        self._fail_when = fail_when

    def __getattr__(self, name):
        return getattr(self._real, name)  # commit / rollback / etc.

    def cursor(self):
        return _FailingCursor(self._real.cursor(), self._fail_when)


class _FailingCursor:
    def __init__(self, cur, fail_when):
        self._cur = cur
        self._fail_when = fail_when

    def __enter__(self):
        self._cur.__enter__()
        return self

    def __exit__(self, *exc):
        return self._cur.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._cur, name)  # fetchone / fetchall / etc.

    def execute(self, sql, params=None):
        if self._fail_when(sql):
            raise psycopg2.OperationalError("forced failure")
        return self._cur.execute(sql, params)


# --- generic (non-pipeline) periodics: UN-3796 ---

_PT_MARKER = f"test_pgperiodic_{uuid.uuid4().hex[:8]}"
_PT_QUEUE = f"{_PT_MARKER}_queue"


def _seed_periodic(
    conn,
    *,
    pg_owned,
    enabled,
    next_run_at,
    cron="0 9 * * *",
    queue=_PT_QUEUE,
    task_args=None,
    task_kwargs=None,
    org_id="",
):
    """Insert one pg_periodic_task row; returns its name."""
    name = f"{_PT_MARKER}_{uuid.uuid4().hex[:6]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pg_periodic_task
              (name, task_name, queue, task_args, task_kwargs, org_id,
               cron_string, enabled, pg_owned, last_run_at, next_run_at,
               created_at, updated_at)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, NULL, %s,
                    now(), now())
            """,
            (
                name,
                "dashboard_metrics.aggregate_from_sources",
                queue,
                json.dumps(task_args if task_args is not None else []),
                json.dumps(task_kwargs if task_kwargs is not None else {}),
                org_id,
                cron,
                enabled,
                pg_owned,
                next_run_at,
            ),
        )
    conn.commit()
    return name


def _periodic_row(conn, name):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_run_at, next_run_at, enabled FROM pg_periodic_task "
            "WHERE name = %s",
            (name,),
        )
        return cur.fetchone()


def _messages_on(conn, queue):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT message FROM pg_queue_message WHERE queue_name = %s", (queue,)
        )
        return [r[0] for r in cur.fetchall()]


@pytest.fixture
def clean_periodic(pg_conn):
    yield pg_conn
    with pg_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM pg_periodic_task WHERE name LIKE %s", (f"{_PT_MARKER}%",)
        )
        cur.execute(
            "DELETE FROM pg_queue_message WHERE queue_name LIKE %s", (f"{_PT_MARKER}%",)
        )
    pg_conn.commit()


class TestDispatchDuePeriodicTasks:
    """UN-3796 — the Beat replacement for everything that isn't a pipeline."""

    def test_due_owned_row_fires_onto_its_own_queue_and_advances(self, clean_periodic):
        conn = clean_periodic
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        name = _seed_periodic(
            conn,
            pg_owned=True,
            enabled=True,
            next_run_at=past,
            task_kwargs={"retention_days": 30},
        )

        assert dispatch_due_periodic_tasks(conn) == 1

        # Enqueued onto the row's OWN queue — the reason this can't reuse the
        # pipeline dispatcher, which targets one fixed queue.
        msgs = _messages_on(conn, _PT_QUEUE)
        assert len(msgs) == 1
        assert msgs[0]["task_name"] == "dashboard_metrics.aggregate_from_sources"
        assert msgs[0]["kwargs"] == {"retention_days": 30}
        assert msgs[0]["queue"] == _PT_QUEUE

        last_run, next_run, _ = _periodic_row(conn, name)
        assert last_run is not None and next_run > last_run

    def test_org_id_is_carried_onto_the_queue_message(self, clean_periodic):
        # org_id is empty for every periodic today (these are global jobs), but the
        # column exists so a later unification with pg_periodic_schedule — which is
        # org-scoped — stays a data migration. Pin that the dispatcher actually
        # threads it through rather than hardcoding "".
        conn = clean_periodic
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        _seed_periodic(
            conn, pg_owned=True, enabled=True, next_run_at=past, org_id="org_acme"
        )
        assert dispatch_due_periodic_tasks(conn) == 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT org_id FROM pg_queue_message WHERE queue_name = %s",
                (_PT_QUEUE,),
            )
            assert cur.fetchone()[0] == "org_acme"

    def test_first_observation_baselines_without_firing(self, clean_periodic):
        # No burst when a row is handed over: Beat fires a new schedule at its next
        # cron match, not immediately, and the hand-over must match that.
        conn = clean_periodic
        name = _seed_periodic(conn, pg_owned=True, enabled=True, next_run_at=None)

        assert dispatch_due_periodic_tasks(conn) == 0
        assert _messages_on(conn, _PT_QUEUE) == []
        last_run, next_run, _ = _periodic_row(conn, name)
        assert last_run is None and next_run is not None

    @pytest.mark.parametrize(
        "pg_owned,enabled", [(False, True), (True, False), (False, False)]
    )
    def test_unowned_or_disabled_rows_never_fire(self, clean_periodic, pg_owned, enabled):
        # Dark by default: until a row is explicitly adopted, Beat is the only firer.
        conn = clean_periodic
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        _seed_periodic(conn, pg_owned=pg_owned, enabled=enabled, next_run_at=past)
        assert dispatch_due_periodic_tasks(conn) == 0
        assert _messages_on(conn, _PT_QUEUE) == []

    def test_not_yet_due_row_does_not_fire(self, clean_periodic):
        conn = clean_periodic
        future = datetime.datetime(2999, 1, 1, tzinfo=datetime.timezone.utc)
        _seed_periodic(conn, pg_owned=True, enabled=True, next_run_at=future)
        assert dispatch_due_periodic_tasks(conn) == 0
        assert _messages_on(conn, _PT_QUEUE) == []

    def test_invalid_cron_disables_the_row_instead_of_looping(self, clean_periodic):
        # Otherwise it is re-selected and re-logs a traceback every tick, forever.
        conn = clean_periodic
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        name = _seed_periodic(
            conn, pg_owned=True, enabled=True, next_run_at=past, cron="not a cron"
        )
        assert dispatch_due_periodic_tasks(conn) == 0
        assert _periodic_row(conn, name)[2] is False  # enabled -> False
        assert _messages_on(conn, _PT_QUEUE) == []

    def test_second_tick_does_not_refire_an_advanced_row(self, clean_periodic):
        # The enqueue and the next_run_at advance share one transaction, so a row
        # that fired is not due again until its next cron match.
        conn = clean_periodic
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        _seed_periodic(conn, pg_owned=True, enabled=True, next_run_at=past)
        assert dispatch_due_periodic_tasks(conn) == 1
        assert dispatch_due_periodic_tasks(conn) == 0
        assert len(_messages_on(conn, _PT_QUEUE)) == 1

    def test_rows_are_isolated_from_each_other(self, clean_periodic):
        # A bad cron on one row must not stop the others firing that tick.
        conn = clean_periodic
        past = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        _seed_periodic(
            conn, pg_owned=True, enabled=True, next_run_at=past, cron="garbage"
        )
        _seed_periodic(conn, pg_owned=True, enabled=True, next_run_at=past)
        assert dispatch_due_periodic_tasks(conn) == 1
        assert len(_messages_on(conn, _PT_QUEUE)) == 1
