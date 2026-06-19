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

import pytest

from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.pg_queue.result_backend import (
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
        the result is committed from a separate connection mid-wait."""
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
