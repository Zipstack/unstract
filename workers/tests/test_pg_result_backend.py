"""Real-PG tests for PgResultBackend — the executor RPC result store.

DB-gated via the ``pg_conn`` fixture (skips when Postgres is unreachable or the
``pg_queue`` migration isn't applied). Pins the request-reply contract: store/get
round-trip (completed + failed), idempotent first-write-wins, absent -> None,
wait returns when present, wait times out, and wait picks up a late write from
*another* connection (the cross-process request-reply path).
"""

import os
import threading
import time
import uuid
from unittest.mock import MagicMock

import psycopg2
import pytest
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.pg_queue.result_backend import (
    _STORE_RETRY_BACKOFF_SECONDS,
    STATUS_COMPLETED,
    STATUS_FAILED,
    PgResultBackend,
)

_MARK = "pgtaskresult-test"


def _key() -> str:
    return f"{_MARK}-{uuid.uuid4()}"


@pytest.fixture
def result_backend(pg_conn):
    rb = PgResultBackend(conn=pg_conn)
    yield rb
    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM pg_task_result WHERE task_id LIKE %s", (f"{_MARK}-%",))
    pg_conn.commit()


class TestStoreGet:
    def test_store_completed_round_trips(self, result_backend):
        k = _key()
        result_backend.store_result(k, result={"success": True, "data": {"x": 1}})
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_COMPLETED
        assert row["result"] == {"success": True, "data": {"x": 1}}
        assert row["error"] == ""  # no-NULL text convention

    def test_store_failed_round_trips(self, result_backend):
        k = _key()
        result_backend.store_result(k, error="boom")
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_FAILED
        assert row["error"] == "boom"
        assert row["result"] is None

    def test_absent_returns_none(self, result_backend):
        assert result_backend.get_result(_key()) is None

    def test_store_idempotent_first_write_wins(self, result_backend):
        """At-least-once redelivery must not clobber a recorded result."""
        k = _key()
        result_backend.store_result(k, result={"v": "first"})
        result_backend.store_result(k, error="second")  # ON CONFLICT DO NOTHING
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_COMPLETED
        assert row["result"] == {"v": "first"}


class TestWait:
    def test_wait_returns_immediately_when_present(self, result_backend):
        k = _key()
        result_backend.store_result(k, result={"ok": True})
        row = result_backend.wait_for_result(k, timeout=5)
        assert row is not None
        assert row["result"] == {"ok": True}

    def test_wait_times_out_returns_none(self, result_backend):
        start = time.monotonic()
        row = result_backend.wait_for_result(_key(), timeout=1, poll_interval=0.2)
        assert row is None
        assert time.monotonic() - start >= 0.9  # waited ~the full timeout

    def test_wait_picks_up_late_write_from_other_conn(self, result_backend):
        """The real request-reply path: the waiter polls on its connection while
        the result is committed from a separate connection mid-wait.
        """
        k = _key()
        os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
        writer = PgResultBackend(conn=create_pg_connection(env_prefix="TEST_DB_"))

        def write_after_delay() -> None:
            time.sleep(0.6)
            writer.store_result(k, result={"late": True})

        t = threading.Thread(target=write_after_delay)
        t.start()
        try:
            row = result_backend.wait_for_result(k, timeout=10, poll_interval=0.2)
        finally:
            t.join()
            writer.close()
        assert row is not None
        assert row["result"] == {"late": True}


# --- Unit: store_result reconnect-retry on a stale cached connection (UN-3659) ---


class _CursorCtx:
    """Mimic a psycopg2 cursor used as a context manager."""

    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *_):
        return False


class TestStoreResultReconnectRetry:
    """store_result self-heals a connection PgBouncer reaped while the executor
    sat idle — the exec-b11ba2f3 hang. Idempotent (ON CONFLICT), so the retry is
    unconditional (no reused-vs-fresh guard, unlike PgQueueClient.send).
    """

    @staticmethod
    def _conn(*, execute_side_effect=None):
        cur = MagicMock()
        if execute_side_effect is not None:
            cur.execute.side_effect = execute_side_effect
        conn = MagicMock()
        conn.closed = 0
        conn.cursor.return_value = _CursorCtx(cur)
        return conn, cur

    @staticmethod
    def _no_sleep(monkeypatch):
        sleep = MagicMock()
        monkeypatch.setattr("queue_backend.pg_queue.result_backend.time.sleep", sleep)
        return sleep

    # Both outcomes go through the same write path — the PR's whole point is that
    # a *failed* task's result (error=) is delivered too, not silently dropped.
    @pytest.mark.parametrize(
        "outcome",
        [{"result": {"ok": True}}, {"error": "boom"}],
        ids=["completed", "failed"],
    )
    def test_stale_conn_retries_and_writes_result(self, monkeypatch, outcome):
        # Cached owned conn reaped while idle fails its first INSERT; the one-shot
        # retry reconnects (factory) and the result is written + committed.
        dead, _ = self._conn(execute_side_effect=psycopg2.OperationalError("idle reap"))
        fresh, fresh_cur = self._conn()
        factory = MagicMock(return_value=fresh)
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        self._no_sleep(monkeypatch)
        rb = PgResultBackend()  # owns its connection
        rb._conn = dead  # simulate a cached (reused) connection

        rb.store_result("k", **outcome)

        dead.close.assert_called_once()  # stale conn discarded
        factory.assert_called_once()  # reconnected exactly once
        fresh_cur.execute.assert_called_once()  # the retry INSERT ran
        fresh.commit.assert_called_once()

    def test_commit_time_reap_retries(self, monkeypatch):
        # An idle reap usually surfaces when the buffered INSERT flushes at
        # conn.commit() (after the cursor yield), not at execute() — that path
        # must retry too.
        dead, _ = self._conn()
        dead.commit.side_effect = psycopg2.OperationalError("reaped at commit")
        fresh, _ = self._conn()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection",
            MagicMock(return_value=fresh),
        )
        self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = dead

        rb.store_result("k", result={"ok": True})  # must self-heal
        dead.close.assert_called_once()
        fresh.commit.assert_called_once()

    def test_injected_connection_not_retried(self, monkeypatch):
        # An injected (caller-owned) conn is never discarded by _cursor, so a
        # retry would re-acquire the same dead handle — short-circuit to re-raise
        # without the spurious backoff sleep.
        conn, _ = self._conn(execute_side_effect=psycopg2.OperationalError("dead"))
        factory = MagicMock()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        sleep = self._no_sleep(monkeypatch)
        rb = PgResultBackend(conn=conn)  # injected -> not owned

        with pytest.raises(psycopg2.OperationalError):
            rb.store_result("k", result={"ok": True})
        factory.assert_not_called()
        sleep.assert_not_called()
        conn.close.assert_not_called()  # caller's connection untouched

    @pytest.mark.parametrize(
        "exc_type", [psycopg2.OperationalError, psycopg2.InterfaceError]
    )
    def test_retries_both_connection_dead_error_types(self, monkeypatch, exc_type):
        # InterfaceError ("connection already closed") is the other stale symptom;
        # narrowing the except to OperationalError alone would re-break the fix.
        dead, _ = self._conn(execute_side_effect=exc_type("dead"))
        fresh, _ = self._conn()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection",
            MagicMock(return_value=fresh),
        )
        self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = dead

        rb.store_result("k", result={"ok": True})  # must not raise
        fresh.commit.assert_called_once()

    def test_backoff_fires_once_on_retry(self, monkeypatch):
        dead, _ = self._conn(execute_side_effect=psycopg2.OperationalError("reap"))
        fresh, _ = self._conn()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection",
            MagicMock(return_value=fresh),
        )
        sleep = self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = dead

        rb.store_result("k", result={"ok": True})
        sleep.assert_called_once_with(_STORE_RETRY_BACKOFF_SECONDS)

    def test_retry_also_fails_reraises_after_one_reconnect(self, monkeypatch):
        dead1, _ = self._conn(execute_side_effect=psycopg2.OperationalError("reap"))
        dead2, _ = self._conn(execute_side_effect=psycopg2.OperationalError("still"))
        factory = MagicMock(return_value=dead2)
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = dead1

        with pytest.raises(psycopg2.OperationalError):
            rb.store_result("k", result={"ok": True})
        factory.assert_called_once()  # exactly one reconnect, no loop

    def test_non_connection_error_not_retried(self, monkeypatch):
        # A logical error (not Operational/Interface) is not a stale-conn symptom.
        bad, _ = self._conn(execute_side_effect=RuntimeError("logic"))
        factory = MagicMock()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        sleep = self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = bad

        with pytest.raises(RuntimeError):
            rb.store_result("k", result={"ok": True})
        factory.assert_not_called()
        sleep.assert_not_called()


class TestStoreResultRealReconnect:
    """DB-gated: store_result REALLY reconnects against live PG (not just mock
    orchestration). Skips when Postgres is unreachable (pg_conn fixture). This is
    the test that fails if _cursor stopped nulling _conn or the reconnect handle
    were unusable — the mock tests can't see that.
    """

    def test_real_reconnect_heals_closed_connection(self, pg_conn, monkeypatch):
        # The owned backend reconnects via result_backend.create_pg_connection;
        # point that at the integration DB (TEST_DB_*), the same one pg_conn uses
        # (the bare DB_* env is the suite's unit-isolation placeholder).
        os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection",
            lambda *a, **k: create_pg_connection(env_prefix="TEST_DB_"),
        )

        key = _key()
        rb = PgResultBackend()  # owned, real connection to the test DB
        try:
            _ = rb.conn  # materialise the connection
            rb._conn.close()  # client-side close -> InterfaceError on next use
            rb.store_result(key, result={"healed": True})  # must self-heal
        finally:
            rb.close()

        # The row really landed — read it back on the fixture's own connection.
        pg_conn.rollback()  # clear any aborted txn before reading
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT result->>'healed' FROM pg_task_result WHERE task_id = %s",
                (key,),
            )
            row = cur.fetchone()
            cur.execute("DELETE FROM pg_task_result WHERE task_id = %s", (key,))
        pg_conn.commit()
        assert row is not None and row[0] == "true"
