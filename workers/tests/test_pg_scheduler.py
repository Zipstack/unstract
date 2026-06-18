"""Tests for the PG scheduler tick (Phase 9, ②b).

Pure tests (cron next-run, payload shape) need no DB. The dispatch behaviour is
exercised against real Postgres via the shared ``pg_conn`` fixture (skips when
unreachable/unmigrated). ``dispatch_due_schedules`` commits, so the real-PG
tests seed + clean up their own rows under a unique org marker.
"""

import datetime
import uuid

import psycopg2
import pytest

from queue_backend.pg_queue.pg_scheduler import (
    SCHEDULER_QUEUE_NAME,
    _build_trigger_payload,
    compute_next_run,
    dispatch_due_schedules,
)


class TestPureHelpers:
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
        with pytest.raises(Exception):
            compute_next_run("not a cron", datetime.datetime(2026, 6, 18, 10, 0, 0))

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
            (pid, _MARKER, str(uuid.uuid4()), "Test ETL", cron, enabled, pg_owned,
             next_run_at),
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
        cur.execute("DELETE FROM pg_periodic_schedule WHERE organization_id = %s", (_MARKER,))
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
        fired = dispatch_due_schedules(_AdvanceFailsConn(conn))

        assert fired == 0
        assert _queued_messages(conn) == []  # INSERT rolled back with the UPDATE
        last_run, next_run = _row(conn, pid)
        assert last_run is None  # not advanced
        assert next_run == past  # unchanged → re-fires next tick (no double-fire)


class _AdvanceFailsConn:
    """Wraps a real connection so the fire-path advance UPDATE raises *after* the
    INSERT — to prove the two are one transaction. Everything else passes through.
    """

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)  # commit / rollback / etc.

    def cursor(self):
        return _AdvanceFailsCursor(self._real.cursor())


class _AdvanceFailsCursor:
    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        self._cur.__enter__()
        return self

    def __exit__(self, *exc):
        return self._cur.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._cur, name)  # fetchone / fetchall / etc.

    def execute(self, sql, params=None):
        # The fire-path advance is the only UPDATE that sets last_run_at.
        if sql.strip().startswith("UPDATE pg_periodic_schedule") and "last_run_at" in sql:
            raise psycopg2.OperationalError("forced advance failure")
        return self._cur.execute(sql, params)
