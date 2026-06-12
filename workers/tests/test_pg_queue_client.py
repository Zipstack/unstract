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
import uuid
from unittest.mock import MagicMock

import psycopg2
import pytest
from queue_backend.pg_queue import PgQueueClient, QueueMessage
from queue_backend.pg_queue.connection import create_pg_connection

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

    def test_send_coerces_missing_org_to_empty_string(self):
        # org_id column is non-null (Django S6553) — None must become "".
        conn, cur = _mock_conn(fetchone=(1,))
        PgQueueClient(conn=conn).send("q1", {"a": 1})
        _, params = cur.execute.call_args.args
        assert params[2] == ""

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

    def test_read_rejects_non_positive_vt(self):
        conn, _ = _mock_conn()
        with pytest.raises(ValueError, match="vt_seconds"):
            PgQueueClient(conn=conn).read("q1", vt_seconds=0)

    def test_read_rejects_non_positive_qty(self):
        conn, _ = _mock_conn()
        with pytest.raises(ValueError, match="qty"):
            PgQueueClient(conn=conn).read("q1", qty=0)

    def test_error_rolls_back_and_reraises(self):
        conn, cur = _mock_conn()
        cur.execute.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            PgQueueClient(conn=conn).send("q1", {"a": 1})
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()


class TestConnectionLifecycle:
    """Recovery + ownership branches of ``_cursor()`` / ``close()``."""

    @staticmethod
    def _owned_client(monkeypatch, *, execute_raises=None):
        cur = MagicMock()
        if execute_raises is not None:
            cur.execute.side_effect = execute_raises
        conn = MagicMock()
        conn.closed = 0
        conn.cursor.return_value = _CursorCtx(cur)
        factory = MagicMock(return_value=conn)
        monkeypatch.setattr(
            "queue_backend.pg_queue.client.create_pg_connection", factory
        )
        return PgQueueClient(), conn, factory

    def test_owned_conn_recovered_on_operational_error(self, monkeypatch):
        client, conn, factory = self._owned_client(
            monkeypatch, execute_raises=psycopg2.OperationalError("dead")
        )
        with pytest.raises(psycopg2.OperationalError):
            client.send("q", {"a": 1})
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()
        assert client._conn is None  # cached handle dropped
        _ = client.conn  # next op reconnects
        assert factory.call_count == 2

    def test_owned_conn_recovered_when_rollback_fails(self, monkeypatch):
        # A non-Operational error whose rollback fails → still treated as dead.
        client, conn, _ = self._owned_client(
            monkeypatch, execute_raises=RuntimeError("boom")
        )
        conn.rollback.side_effect = psycopg2.DatabaseError("socket gone")
        with pytest.raises(RuntimeError):
            client.send("q", {"a": 1})
        conn.close.assert_called_once()
        assert client._conn is None

    def test_injected_conn_never_closed_on_error(self):
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("dead")
        conn = MagicMock()
        conn.closed = 0
        conn.cursor.return_value = _CursorCtx(cur)
        client = PgQueueClient(conn=conn)
        with pytest.raises(psycopg2.OperationalError):
            client.send("q", {"a": 1})
        conn.rollback.assert_called_once()
        conn.close.assert_not_called()
        assert client._conn is conn  # caller's connection untouched

    def test_close_closes_owned_not_injected(self, monkeypatch):
        client, conn, _ = self._owned_client(monkeypatch)
        _ = client.conn  # lazily create
        client.close()
        conn.close.assert_called_once()
        assert client._conn is None

        injected = MagicMock()
        PgQueueClient(conn=injected).close()
        injected.close.assert_not_called()


class TestCreatePgConnection:
    """Unit coverage for the connection factory (no real DB)."""

    def test_reads_env_prefix_and_sets_search_path(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            "queue_backend.pg_queue.connection.psycopg2.connect",
            lambda **kw: captured.update(kw) or object(),
        )
        # Password is a runtime token (not a hard-coded literal) so it isn't
        # mistaken for a credential, while still proving the env is read.
        secret = uuid.uuid4().hex
        for k, v in {
            "HOST": "h",
            "PORT": "6432",
            "NAME": "n",
            "USER": "u",
            "PASSWORD": secret,
            "SCHEMA": "s",
        }.items():
            monkeypatch.setenv(f"DB_{k}", v)
        create_pg_connection()
        assert captured["host"] == "h"
        assert captured["port"] == "6432"
        assert captured["dbname"] == "n"
        assert captured["user"] == "u"
        assert captured["password"] == secret
        assert captured["options"] == "-c search_path=s"

    def test_env_prefix_override(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            "queue_backend.pg_queue.connection.psycopg2.connect",
            lambda **kw: captured.update(kw) or object(),
        )
        monkeypatch.setenv("TEST_DB_HOST", "test-host")
        create_pg_connection(env_prefix="TEST_DB_")
        assert captured["host"] == "test-host"

    def test_connect_failure_is_logged_and_reraised(self, monkeypatch, caplog):
        import logging

        def boom(**_):
            raise psycopg2.OperationalError("nope")

        monkeypatch.setattr(
            "queue_backend.pg_queue.connection.psycopg2.connect", boom
        )
        with (
            caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.connection"),
            pytest.raises(psycopg2.OperationalError),
        ):
            create_pg_connection()
        assert "failed to connect" in caplog.text


# --- Integration: real Postgres (pg_conn fixture from conftest.py) ---


@pytest.fixture
def queue_name(pg_conn):
    # Unique per test for isolation; clean up rows afterwards.
    name = f"test_q_{os.getpid()}_{int(time.time() * 1000)}"
    yield name
    # A failed test body can leave the connection in an aborted transaction;
    # roll back first so this cleanup doesn't raise InFailedSqlTransaction.
    pg_conn.rollback()
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
        # Second connection (TEST_DB_HOST already set by the pg_conn fixture).
        conn_b = create_pg_connection(env_prefix="TEST_DB_")
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
