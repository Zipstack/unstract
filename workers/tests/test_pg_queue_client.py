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

import logging
import os
import time
import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import psycopg2
import pytest
from queue_backend.fairness import DEFAULT_PRIORITY, MAX_PRIORITY, MIN_PRIORITY
from queue_backend.pg_queue import PgQueueClient, QueueMessage
from queue_backend.pg_queue.client import _SEND_RETRY_BACKOFF_SECONDS
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.pg_queue.reaper import rearm_expired_claims
from queue_backend.pg_queue.schema import qualified

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
        assert f"INSERT INTO {qualified('pg_queue_message')}" in sql
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

    def test_send_writes_priority(self):
        # Default is the neutral DEFAULT_PRIORITY; an explicit value passes through.
        conn, cur = _mock_conn(fetchone=(1,))
        PgQueueClient(conn=conn).send("q1", {"a": 1})
        sql, params = cur.execute.call_args.args
        assert "priority" in sql
        assert params[3] == DEFAULT_PRIORITY

        conn, cur = _mock_conn(fetchone=(2,))
        PgQueueClient(conn=conn).send("q1", {"a": 1}, priority=9)
        _, params = cur.execute.call_args.args
        assert params[3] == 9

    @pytest.mark.parametrize("bad", [0, -1, 11, 99])
    def test_send_rejects_out_of_range_priority(self, bad):
        # An out-of-range priority would silently jump/sink the row in the
        # priority DESC claim order — reject at the write boundary.
        conn, _ = _mock_conn(fetchone=(1,))
        client = PgQueueClient(conn=conn)
        with pytest.raises(ValueError, match="priority out of range"):
            client.send("q1", {"a": 1}, priority=bad)

    def test_read_runs_skip_locked_dequeue(self):
        conn, cur = _mock_conn(fetchall=[(7, {"k": "v"}, 1)])
        msgs = PgQueueClient(conn=conn).read("q1", vt_seconds=15, qty=3)
        sql, params = cur.execute.call_args.args
        assert "FOR UPDATE SKIP LOCKED" in sql
        assert f"UPDATE {qualified('pg_queue_message')}" in sql
        assert "ORDER BY priority DESC" in sql  # fairness L3 claim order
        # Param order follows the %s positions: queue_name, qty, vt_seconds.
        assert params == ("q1", 3, 15)
        assert msgs == [QueueMessage(msg_id=7, message={"k": "v"}, read_ct=1)]
        conn.commit.assert_called_once()

    def test_delete_returns_true_when_row_removed(self):
        conn, cur = _mock_conn(rowcount=1)
        assert PgQueueClient(conn=conn).delete(7) is True
        sql, params = cur.execute.call_args.args
        assert f"DELETE FROM {qualified('pg_queue_message')}" in sql
        assert params == (7,)
        conn.commit.assert_called_once()

    def test_delete_returns_false_when_no_row(self):
        conn, _ = _mock_conn(rowcount=0)
        assert PgQueueClient(conn=conn).delete(999) is False

    def test_set_vt_reparks_message(self):
        conn, cur = _mock_conn(rowcount=1)
        assert PgQueueClient(conn=conn).set_vt(42, 300) is True
        sql, params = cur.execute.call_args.args
        assert f"UPDATE {qualified('pg_queue_message')}" in sql
        assert "SET vt = now() + make_interval(secs => %s)" in sql
        assert "read_ct" not in sql  # re-park must NOT bump the delivery count
        assert params == (300, 42)
        conn.commit.assert_called_once()

    def test_set_vt_returns_false_when_no_row(self):
        conn, _ = _mock_conn(rowcount=0)
        assert PgQueueClient(conn=conn).set_vt(999, 300) is False

    def test_set_vt_rejects_non_positive(self):
        conn, _ = _mock_conn()
        client = PgQueueClient(conn=conn)
        with pytest.raises(ValueError, match="vt_seconds"):
            client.set_vt(1, 0)

    def test_read_rejects_non_positive_vt(self):
        conn, _ = _mock_conn()
        client = PgQueueClient(conn=conn)
        with pytest.raises(ValueError, match="vt_seconds"):
            client.read("q1", vt_seconds=0)

    def test_read_rejects_non_positive_qty(self):
        conn, _ = _mock_conn()
        client = PgQueueClient(conn=conn)
        with pytest.raises(ValueError, match="qty"):
            client.read("q1", qty=0)

    def test_error_rolls_back_and_reraises(self):
        conn, cur = _mock_conn()
        cur.execute.side_effect = RuntimeError("boom")
        client = PgQueueClient(conn=conn)
        with pytest.raises(RuntimeError):
            client.send("q1", {"a": 1})
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
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
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


class TestSendReconnectRetry:
    """``send()``'s one-shot reconnect-retry for a reused, idle-reaped connection.

    A cached connection can be reaped server-side (PgBouncer
    ``server_idle_timeout`` / failover) while idle between sends; the first
    statement after the gap then fails. ``send()`` retries ONCE — but only when
    the failing connection was **reused** (cached + owned), so the ``INSERT``
    (which is not idempotent) can't be double-enqueued: a reused conn that dies
    on its first statement was reaped while idle and never ran the write.
    """

    @staticmethod
    def _conn(*, execute_side_effect=None, fetchone=(1,)):
        cur = MagicMock()
        if execute_side_effect is not None:
            cur.execute.side_effect = execute_side_effect
        cur.fetchone.return_value = fetchone
        conn = MagicMock()
        conn.closed = 0
        conn.cursor.return_value = _CursorCtx(cur)
        return conn, cur

    @staticmethod
    def _no_sleep(monkeypatch):
        sleep = MagicMock()
        monkeypatch.setattr("queue_backend.pg_queue.client.time.sleep", sleep)
        return sleep

    @pytest.mark.parametrize(
        "exc_type", [psycopg2.OperationalError, psycopg2.InterfaceError]
    )
    def test_reused_stale_conn_retries_and_succeeds(self, monkeypatch, caplog, exc_type):
        # Cached owned conn reaped while idle fails its first statement; the
        # one-shot retry reconnects (factory) and the INSERT lands. Exercise
        # BOTH connection-dead error types — InterfaceError is the more likely
        # stale symptom and is otherwise never covered, so narrowing the except
        # to OperationalError alone would silently pass.
        dead, _ = self._conn(execute_side_effect=exc_type("idle reap"))
        fresh, fresh_cur = self._conn(fetchone=(77,))
        factory = MagicMock(return_value=fresh)
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
        sleep = self._no_sleep(monkeypatch)
        client = PgQueueClient()  # owns its connection
        client._conn = dead  # simulate a cached (reused) connection

        with caplog.at_level(logging.WARNING, logger="queue_backend.pg_queue.client"):
            msg_id = client.send("q", {"a": 1}, org_id="org-7", priority=9)
        assert msg_id == 77  # the retry's INSERT
        dead.close.assert_called_once()  # stale conn discarded
        factory.assert_called_once()  # reconnected exactly once
        # The backoff actually fired (don't just discard the _no_sleep mock).
        sleep.assert_called_once_with(_SEND_RETRY_BACKOFF_SECONDS)
        # The retry's INSERT carries the passthrough params — a params-drop on
        # the reconnect path would be caught here (assert on the FRESH cursor).
        _, params = fresh_cur.execute.call_args.args
        assert params[0] == "q"  # queue_name
        assert params[2] == "org-7"  # org_id
        assert params[3] == 9  # priority
        # The connection-level failure surfaced as a WARNING on the retry.
        assert any(r.levelno == logging.WARNING for r in caplog.records)
        assert "retrying once" in caplog.text

    def test_fresh_conn_failure_does_not_retry(self, monkeypatch):
        # First-ever send (self._conn is None) is on a FRESH conn — a failure
        # there is a genuine error / ambiguous; must NOT retry (could duplicate).
        dead, _ = self._conn(execute_side_effect=psycopg2.OperationalError("down"))
        factory = MagicMock(return_value=dead)
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
        sleep = self._no_sleep(monkeypatch)
        client = PgQueueClient()

        with pytest.raises(psycopg2.OperationalError):
            client.send("q", {"a": 1})
        factory.assert_called_once()  # created once, NOT retried
        sleep.assert_not_called()

    def test_injected_conn_not_retried(self, monkeypatch):
        # An injected (caller-owned) conn is never recycled, so retrying can't
        # reconnect — and isn't ours to retry. Re-raise without retry.
        conn, _ = self._conn(execute_side_effect=psycopg2.OperationalError("dead"))
        sleep = self._no_sleep(monkeypatch)
        client = PgQueueClient(conn=conn)

        with pytest.raises(psycopg2.OperationalError):
            client.send("q", {"a": 1})
        sleep.assert_not_called()
        conn.close.assert_not_called()  # caller's connection untouched

    def test_retry_failure_reraises_once(self, monkeypatch):
        # If the reconnected attempt also fails, raise — exactly one reconnect,
        # no loop.
        dead1, _ = self._conn(execute_side_effect=psycopg2.OperationalError("reap"))
        dead2, _ = self._conn(execute_side_effect=psycopg2.OperationalError("still"))
        factory = MagicMock(return_value=dead2)
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
        self._no_sleep(monkeypatch)
        client = PgQueueClient()
        client._conn = dead1

        with pytest.raises(psycopg2.OperationalError):
            client.send("q", {"a": 1})
        factory.assert_called_once()  # one reconnect only

    def test_reused_conn_non_connection_error_not_retried(self, monkeypatch):
        # A logical error (not Operational/Interface) on a reused conn is not a
        # stale-connection symptom → re-raise, no reconnect.
        bad, _ = self._conn(execute_side_effect=RuntimeError("logic"))
        factory = MagicMock()
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
        sleep = self._no_sleep(monkeypatch)
        client = PgQueueClient()
        client._conn = bad

        with pytest.raises(RuntimeError):
            client.send("q", {"a": 1})
        factory.assert_not_called()
        sleep.assert_not_called()


class TestDeleteReconnectRetry:
    """``delete()``'s (ack) one-shot reconnect-retry — the systematic first-write-
    after-idle site: the consumer connection idles for the whole task wall-clock,
    so a reaped conn kills the ack and redelivers an ALREADY-COMPLETED message
    (duplicate work / double-fired callback). Unlike ``send()`` the DELETE is
    idempotent, so retrying is safe even post-commit.
    """

    @staticmethod
    def _conn(*, execute_side_effect=None, rowcount=1):
        cur = MagicMock()
        if execute_side_effect is not None:
            cur.execute.side_effect = execute_side_effect
        cur.rowcount = rowcount
        conn = MagicMock()
        conn.closed = 0
        conn.cursor.return_value = _CursorCtx(cur)
        return conn, cur

    @staticmethod
    def _no_sleep(monkeypatch):
        sleep = MagicMock()
        monkeypatch.setattr("queue_backend.pg_queue.client.time.sleep", sleep)
        return sleep

    @pytest.mark.parametrize(
        "exc_type", [psycopg2.OperationalError, psycopg2.InterfaceError]
    )
    def test_reused_stale_conn_retries_and_acks(self, monkeypatch, caplog, exc_type):
        dead, _ = self._conn(execute_side_effect=exc_type("idle reap"))
        fresh, fresh_cur = self._conn(rowcount=1)
        factory = MagicMock(return_value=fresh)
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
        sleep = self._no_sleep(monkeypatch)
        client = PgQueueClient()
        client._conn = dead  # cached (reused) connection

        with caplog.at_level(logging.WARNING, logger="queue_backend.pg_queue.client"):
            assert client.delete(42) is True  # ack landed on the retry
        dead.close.assert_called_once()  # stale conn discarded
        factory.assert_called_once()  # reconnected exactly once
        sleep.assert_called_once_with(_SEND_RETRY_BACKOFF_SECONDS)
        _, params = fresh_cur.execute.call_args.args
        assert params == (42,)  # the msg_id passed through to the retry
        assert "retrying the ack once" in caplog.text

    def test_fresh_conn_failure_does_not_retry(self, monkeypatch):
        dead, _ = self._conn(execute_side_effect=psycopg2.OperationalError("down"))
        factory = MagicMock(return_value=dead)
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
        sleep = self._no_sleep(monkeypatch)
        client = PgQueueClient()

        with pytest.raises(psycopg2.OperationalError):
            client.delete(1)
        factory.assert_called_once()  # created once, NOT retried
        sleep.assert_not_called()

    def test_injected_conn_not_retried(self, monkeypatch):
        conn, _ = self._conn(execute_side_effect=psycopg2.OperationalError("dead"))
        self._no_sleep(monkeypatch)
        client = PgQueueClient(conn=conn)

        with pytest.raises(psycopg2.OperationalError):
            client.delete(1)
        conn.close.assert_not_called()  # caller's connection untouched

    def test_reused_conn_non_connection_error_not_retried(self, monkeypatch):
        # A logical error (not Operational/Interface) on a reused conn is not a
        # stale-connection symptom → re-raise, no reconnect (parity with send()).
        bad, _ = self._conn(execute_side_effect=RuntimeError("logic"))
        factory = MagicMock()
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
        sleep = self._no_sleep(monkeypatch)
        client = PgQueueClient()
        client._conn = bad

        with pytest.raises(RuntimeError):
            client.delete(1)
        factory.assert_not_called()
        sleep.assert_not_called()

    def test_retry_failure_reraises_once(self, monkeypatch):
        # The retry is bounded to exactly one reconnect: if the reconnected conn
        # also dies, re-raise (no loop) — parity with send().
        dead1, _ = self._conn(execute_side_effect=psycopg2.OperationalError("reap"))
        dead2, _ = self._conn(execute_side_effect=psycopg2.OperationalError("still"))
        factory = MagicMock(return_value=dead2)
        monkeypatch.setattr("queue_backend.pg_queue.client.create_pg_connection", factory)
        self._no_sleep(monkeypatch)
        client = PgQueueClient()
        client._conn = dead1

        with pytest.raises(psycopg2.OperationalError):
            client.delete(1)
        factory.assert_called_once()  # one reconnect only, no loop


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

        monkeypatch.setattr("queue_backend.pg_queue.connection.psycopg2.connect", boom)
        with (
            caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.connection"),
            pytest.raises(psycopg2.OperationalError),
        ):
            create_pg_connection()
        assert "failed to connect" in caplog.text


# --- Integration: real Postgres (pg_conn fixture from conftest.py) ---


@pytest.fixture
def queue_name(pg_conn):
    # Unique per test for isolation (uuid — a ms timestamp collides when
    # fast tests run within the same millisecond); clean up rows afterwards.
    name = f"test_q_{os.getpid()}_{uuid.uuid4().hex}"
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

    def test_priority_orders_dequeue(self, pg_conn, queue_name):
        # Higher priority is claimed first; FIFO (msg_id) within a priority —
        # regardless of enqueue order. Read one at a time (the default
        # batch_size=1 path), so each claim selects the current top-priority row.
        client = PgQueueClient(conn=pg_conn)
        client.send(queue_name, {"n": "low1"}, priority=1)
        client.send(queue_name, {"n": "high"}, priority=9)
        client.send(queue_name, {"n": "low2"}, priority=1)
        client.send(queue_name, {"n": "mid"}, priority=5)
        claimed = []
        for _ in range(4):
            msgs = client.read(queue_name, vt_seconds=30, qty=1)
            assert len(msgs) == 1
            claimed.append(msgs[0].message["n"])
            client.delete(msgs[0].msg_id)
        assert claimed == ["high", "mid", "low1", "low2"]

    def test_priority_orders_batch_claim(self, pg_conn, queue_name):
        # A batched claim (qty > 1) returns the batch in priority order too —
        # the CTE re-sorts RETURNING, which is otherwise unspecified.
        client = PgQueueClient(conn=pg_conn)
        client.send(queue_name, {"n": "a"}, priority=1)
        client.send(queue_name, {"n": "b"}, priority=9)
        client.send(queue_name, {"n": "c"}, priority=5)
        msgs = client.read(queue_name, vt_seconds=30, qty=10)
        assert [m.message["n"] for m in msgs] == ["b", "c", "a"]

    def test_batch_fifo_within_priority_band(self, pg_conn, queue_name):
        # Two rows per band, interleaved enqueue → strict (band DESC, msg_id ASC).
        client = PgQueueClient(conn=pg_conn)
        for label, prio in [("9a", 9), ("1a", 1), ("9b", 9), ("1b", 1)]:
            client.send(queue_name, {"n": label}, priority=prio)
        msgs = client.read(queue_name, vt_seconds=30, qty=10)
        assert [m.message["n"] for m in msgs] == ["9a", "9b", "1a", "1b"]

    def test_visible_low_priority_beats_invisible_high(self, pg_conn, queue_name):
        # A claimed-but-unacked high-priority row (future vt) must not block a
        # visible lower-priority row — exercises vt × priority interaction.
        client = PgQueueClient(conn=pg_conn)
        high_id = client.send(queue_name, {"n": "high"}, priority=9)
        # Claim the high row → its vt jumps 30s ahead (now invisible).
        assert [m.msg_id for m in client.read(queue_name, vt_seconds=30, qty=1)] == [
            high_id
        ]
        client.send(queue_name, {"n": "low"}, priority=1)
        msgs = client.read(queue_name, vt_seconds=30, qty=1)
        assert [m.message["n"] for m in msgs] == ["low"]

    def test_concurrent_claims_never_exceed_qty(self, pg_conn, queue_name):
        # The CTE FROM-join claims exactly qty even under concurrent writers;
        # the old IN(SELECT ... LIMIT) form could over-claim via EvalPlanQual.
        # Two readers drain a backlog in parallel; no batch may exceed qty.
        import threading

        client_a = PgQueueClient(conn=pg_conn)
        for i in range(50):
            client_a.send(queue_name, {"i": i})
        conn_b = create_pg_connection(env_prefix="TEST_DB_")
        violations: list[int] = []

        def drain(client):
            while True:
                msgs = client.read(queue_name, vt_seconds=30, qty=1)
                if not msgs:
                    return
                if len(msgs) > 1:  # over-claim → the bug this rewrite fixes
                    violations.append(len(msgs))
                for m in msgs:
                    client.delete(m.msg_id)

        try:
            worker = threading.Thread(target=drain, args=(PgQueueClient(conn=conn_b),))
            worker.start()
            drain(client_a)
            worker.join(timeout=15)
            # Assert termination: a hung drain must fail the test, not pass
            # silently while conn_b.close() races its in-flight queries.
            assert not worker.is_alive(), "drain worker did not finish within 15s"
        finally:
            conn_b.close()
        assert violations == []

    def test_db_check_constraint_matches_fairness_bounds(self, pg_conn, queue_name):
        # The DB CheckConstraint is the backstop for any raw/ORM writer that
        # bypasses send()'s guard. It also pins the constraint to the app's
        # fairness range: models.py and fairness.py live in separate codebases
        # that can't import each other, so this boundary check is the guard
        # against silent drift — in-range accepted, just outside rejected.
        def _raw_insert(prio):
            with pg_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pg_queue_message "
                    "(queue_name, message, org_id, priority, enqueued_at, vt, read_ct) "
                    "VALUES (%s, '{}'::jsonb, '', %s, now(), now(), 0)",
                    (queue_name, prio),
                )

        for prio in (MIN_PRIORITY, MAX_PRIORITY):  # in-range boundaries accepted
            _raw_insert(prio)
        pg_conn.commit()
        for prio in (MIN_PRIORITY - 1, MAX_PRIORITY + 1):  # out-of-range rejected
            with pytest.raises(psycopg2.errors.CheckViolation):
                _raw_insert(prio)
            pg_conn.rollback()

    def test_vt_expiry_redelivers_via_reaper(self, pg_conn, queue_name):
        # UN-3445: redelivery is now EXPLICIT (reaper re-arm), not implicit in the
        # claim. A claimed row whose vt expired is state='claimed' and INVISIBLE to
        # the state='ready' claim — so a bare re-read returns nothing — until the
        # reaper's rearm_expired_claims flips it back to 'ready'. This replaces the
        # old implicit `vt<=now()` self-heal in _dequeue_sql.
        client = PgQueueClient(conn=pg_conn)
        client.send(queue_name, {"n": 1})
        claimed = client.read(queue_name, vt_seconds=1, qty=10)
        assert len(claimed) == 1
        time.sleep(1.3)  # let the lease (vt) expire — worker is "dead"

        # Before re-arm: the expired-but-claimed row is not claimable.
        assert client.read(queue_name, vt_seconds=30, qty=10) == []

        # Reaper re-arms the expired claim → row returns to 'ready'.
        assert rearm_expired_claims(pg_conn) == 1
        # Idempotent: a second tick re-arms nothing (row is 'ready' now) — the
        # double-tick safety property under overlapping reaper cycles.
        assert rearm_expired_claims(pg_conn) == 0

        # Now the next consumer re-claims it (crash redelivery restored).
        again = client.read(queue_name, vt_seconds=30, qty=10)
        assert [m.msg_id for m in again] == [c.msg_id for c in claimed]

    def test_reaper_does_not_rearm_a_live_lease(self, pg_conn, queue_name):
        # A live worker keeps vt in the future (renewal), so the re-arm's
        # `vt<=now()` predicate never matches it — no premature redelivery.
        client = PgQueueClient(conn=pg_conn)
        client.send(queue_name, {"n": 1})
        claimed = client.read(queue_name, vt_seconds=30, qty=10)  # long lease
        assert len(claimed) == 1
        assert rearm_expired_claims(pg_conn) == 0  # vt not expired → untouched
        assert client.read(queue_name, vt_seconds=30, qty=10) == []  # still claimed

    def test_state_check_constraint_matches_enum(self, pg_conn, queue_name):
        # Drift guard (mirrors test_db_check_constraint_matches_fairness_bounds):
        # the DB CheckConstraint must accept exactly the QueueMessageState values
        # and reject anything else — the backstop no writer can bypass, and the
        # cross-codebase contract for the shared enum.
        from unstract.core.data_models import QueueMessageState

        client = PgQueueClient(conn=pg_conn)
        mid = client.send(queue_name, {"n": 1})

        def _set_state(value):
            with pg_conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {qualified('pg_queue_message')} "
                    "SET state = %s WHERE msg_id = %s",
                    (value, mid),
                )

        for state in QueueMessageState:  # every enum value accepted
            _set_state(state.value)
        pg_conn.commit()
        with pytest.raises(psycopg2.errors.CheckViolation):  # anything else rejected
            _set_state("bogus")
        pg_conn.rollback()

    def test_inflight_backfill_sql_classifies_by_vt(self, pg_conn, queue_name):
        # Behavioural half of migration 0014's deploy-safety backfill (the
        # structural guard is backend/pg_queue/tests/test_migration_0014_backfill).
        # After AddField sets every row 'ready', the backfill re-classifies genuinely
        # in-flight (future-vt) rows to 'claimed'; idle (past-vt) rows stay 'ready'.
        tbl = qualified("pg_queue_message")
        with pg_conn.cursor() as cur:
            insert = (
                f"INSERT INTO {tbl} "
                "(queue_name, message, org_id, priority, enqueued_at, vt, read_ct, "
                "state) VALUES (%s, '{}'::jsonb, '', 5, now(), now() + %s, 0, 'ready')"
                " RETURNING msg_id"
            )
            cur.execute(insert, (queue_name, timedelta(hours=1)))  # in-flight
            inflight = cur.fetchone()[0]
            cur.execute(insert, (queue_name, timedelta(hours=-1)))  # idle
            idle = cur.fetchone()[0]
            # the exact statement migration 0014 runs
            cur.execute(f"UPDATE {tbl} SET state = 'claimed' WHERE vt > now()")
            cur.execute(
                f"SELECT msg_id, state FROM {tbl} WHERE msg_id = ANY(%s)",
                ([inflight, idle],),
            )
            states = dict(cur.fetchall())
        pg_conn.rollback()
        assert states[inflight] == "claimed"  # future vt → invisible until lease ends
        assert states[idle] == "ready"  # past vt → immediately claimable

    def test_claim_writes_state_claimed_for_the_whole_batch(self, pg_conn, queue_name):
        # The write half of the machine: a batch claim (qty>1) sets EVERY returned
        # row to 'claimed', while an unclaimed row stays 'ready'.
        client = PgQueueClient(conn=pg_conn)
        ids = [client.send(queue_name, {"n": i}) for i in range(3)]
        claimed = client.read(queue_name, vt_seconds=30, qty=2)  # claim 2 of 3
        assert len(claimed) == 2
        claimed_ids = {m.msg_id for m in claimed}
        with pg_conn.cursor() as cur:
            cur.execute(
                f"SELECT msg_id, state FROM {qualified('pg_queue_message')} "
                "WHERE msg_id = ANY(%s)",
                (ids,),
            )
            state_by_id = dict(cur.fetchall())
        for mid in ids:
            expected = "claimed" if mid in claimed_ids else "ready"
            assert state_by_id[mid] == expected

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
