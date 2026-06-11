"""Tests for the PG-queue client (``queue_backend.pg_queue``).

Two layers:

1. **Unit** (mocked connection) — ``send`` / ``read`` / ``delete`` issue
   the right SQL + params and commit. Always runs, no DB needed.

2. **Integration** (real Postgres) — exercises the actual ``SKIP LOCKED``
   + visibility-timeout semantics against a live DB. Skips gracefully if
   Postgres isn't reachable or the ``pg_queue`` migration hasn't been
   applied.
"""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock

import pytest
from queue_backend.pg_queue import PgQueueClient, QueueMessage

# --- Unit: SQL shape against a mocked connection ---


class _CursorCtx:
    """Mimic a psycopg2 cursor used as a context manager."""

    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *_):
        return False


def _mock_conn(*, fetchone=None, fetchall=None, rowcount=0):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value = _CursorCtx(cur)
    return conn, cur


class TestPgQueueClientUnit:
    def test_send_inserts_and_returns_msg_id(self):
        conn, cur = _mock_conn(fetchone=(42,))
        msg_id = PgQueueClient(conn=conn).send("q1", {"a": 1}, org_id="org-9")
        assert msg_id == 42
        sql, params = cur.execute.call_args.args
        assert "INSERT INTO pg_queue_message" in sql
        assert params[0] == "q1"
        assert params[2] == "org-9"
        assert '"a": 1' in params[1]  # message JSON-serialised
        conn.commit.assert_called_once()

    def test_read_runs_skip_locked_dequeue(self):
        conn, cur = _mock_conn(fetchall=[(7, {"k": "v"})])
        msgs = PgQueueClient(conn=conn).read("q1", vt_seconds=15, qty=3)
        sql, params = cur.execute.call_args.args
        assert "FOR UPDATE SKIP LOCKED" in sql
        assert "UPDATE pg_queue_message" in sql
        # Param order follows the %s positions: vt_seconds, queue_name, qty.
        assert params == (15, "q1", 3)
        assert msgs == [QueueMessage(msg_id=7, message={"k": "v"})]
        conn.commit.assert_called_once()

    def test_delete_returns_true_when_row_removed(self):
        conn, cur = _mock_conn(rowcount=1)
        assert PgQueueClient(conn=conn).delete(7) is True
        sql, params = cur.execute.call_args.args
        assert "DELETE FROM pg_queue_message" in sql
        assert params == (7,)
        conn.commit.assert_called_once()

    def test_delete_returns_false_when_no_row(self):
        conn, _ = _mock_conn(rowcount=0)
        assert PgQueueClient(conn=conn).delete(999) is False


# --- Integration: real Postgres ---


def _integration_conn():
    # Target the dev DB via dedicated TEST_DB_* env (dev defaults). We
    # deliberately do NOT read the generic DB_* vars: the test suite's
    # conftest sets DB_USER=test etc. for unit isolation, which would
    # point this real-DB connection at nonexistent credentials.
    import psycopg2

    return psycopg2.connect(
        host=os.getenv("TEST_DB_HOST", "127.0.0.1"),
        port=os.getenv("TEST_DB_PORT", "5432"),
        dbname=os.getenv("TEST_DB_NAME", "unstract_db"),
        user=os.getenv("TEST_DB_USER", "unstract_dev"),
        password=os.getenv("TEST_DB_PASSWORD", "unstract_pass"),
        options=f"-c search_path={os.getenv('TEST_DB_SCHEMA', 'unstract')}",
    )


@pytest.fixture
def pg_conn():
    try:
        conn = _integration_conn()
    except Exception as exc:  # noqa: BLE001 — any connect failure → skip
        pytest.skip(f"Postgres not reachable: {exc}")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_queue_message')")
        (table,) = cur.fetchone()
    if table is None:
        conn.close()
        pytest.skip("pg_queue migration not applied (run backend migrate)")
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def queue_name(pg_conn):
    # Unique per test for isolation; clean up rows afterwards.
    name = f"test_q_{os.getpid()}_{int(time.time() * 1000)}"
    yield name
    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM pg_queue_message WHERE queue_name = %s", (name,))
    pg_conn.commit()


class TestPgQueueClientIntegration:
    def test_send_read_delete_roundtrip(self, pg_conn, queue_name):
        client = PgQueueClient(conn=pg_conn)
        msg_id = client.send(queue_name, {"hello": "world"})
        msgs = client.read(queue_name, vt_seconds=30, qty=10)
        assert [m.msg_id for m in msgs] == [msg_id]
        assert msgs[0].message == {"hello": "world"}
        assert client.delete(msg_id) is True
        assert client.read(queue_name, vt_seconds=30, qty=10) == []  # gone

    def test_read_hides_message_for_vt(self, pg_conn, queue_name):
        client = PgQueueClient(conn=pg_conn)
        client.send(queue_name, {"n": 1})
        assert len(client.read(queue_name, vt_seconds=30, qty=10)) == 1
        # Second read within vt sees nothing.
        assert client.read(queue_name, vt_seconds=30, qty=10) == []

    def test_vt_expiry_redelivers(self, pg_conn, queue_name):
        client = PgQueueClient(conn=pg_conn)
        client.send(queue_name, {"n": 1})
        claimed = client.read(queue_name, vt_seconds=1, qty=10)
        assert len(claimed) == 1
        time.sleep(1.3)  # let vt expire
        again = client.read(queue_name, vt_seconds=30, qty=10)
        assert [m.msg_id for m in again] == [c.msg_id for c in claimed]

    def test_no_double_delivery_across_readers(self, pg_conn, queue_name):
        """Two readers never claim the same message (SKIP LOCKED + vt)."""
        client_a = PgQueueClient(conn=pg_conn)
        for i in range(5):
            client_a.send(queue_name, {"i": i})
        conn_b = _integration_conn()
        try:
            client_b = PgQueueClient(conn=conn_b)
            ids_a = {m.msg_id for m in client_a.read(queue_name, vt_seconds=30, qty=3)}
            ids_b = {m.msg_id for m in client_b.read(queue_name, vt_seconds=30, qty=3)}
            assert ids_a.isdisjoint(ids_b)  # no double-delivery
            assert len(ids_a) + len(ids_b) == 5  # all delivered exactly once
        finally:
            conn_b.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
