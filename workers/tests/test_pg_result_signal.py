"""Unit tests for the Redis ready-signal path of PgResultBackend.

These are pure-logic tests (no real Postgres/Redis): the DB read (``get_result``)
and the Redis client (``_get_result_redis_client``) are stubbed, so they pin the
*routing and safety* contract of ``PG_RESULT_SIGNAL_BACKEND=redis`` independently of
infrastructure — complementing the real-PG round-trip in
``test_pg_result_backend.py``.

Contract pinned here:
- flag routing: ``poll`` (default) uses the historical backoff poll unchanged;
  ``redis`` uses the BLPOP fast-path.
- correctness never depends on the signal: publish-before-wait race is closed by an
  immediate check; a missing token / dead Redis degrades to the poll path; the DB is
  always the source of truth.
- ``store_result`` signals only in redis mode; ``_signal_ready`` never raises and
  sends only the reply key (no result payload / PII) to Redis.
"""

from __future__ import annotations

import threading
import time
import uuid
from unittest.mock import MagicMock

import pytest
from queue_backend.pg_queue import result_backend as rb_mod
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.pg_queue.result_backend import (
    PgResultBackend,
    _ready_key,
    _signal_backend,
    _signal_ready,
)

_ROW = {"status": "completed", "result": {"ok": True}, "error": ""}


@pytest.fixture(autouse=True)
def _reset_redis_singleton(monkeypatch):
    """Isolate the module-level Redis client cache between tests."""
    monkeypatch.setattr(rb_mod, "_redis_client_singleton", None, raising=False)
    monkeypatch.setattr(rb_mod, "_redis_client_unavailable", False, raising=False)
    yield


def _backend_with_get_result(returns):
    """A PgResultBackend whose get_result yields ``returns`` (a list = one per call,
    or a single value repeated). No DB is touched."""
    rb = PgResultBackend()
    if isinstance(returns, list):
        rb.get_result = MagicMock(side_effect=returns)  # type: ignore[method-assign]
    else:
        rb.get_result = MagicMock(return_value=returns)  # type: ignore[method-assign]
    return rb


class TestSignalBackendFlag:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, "poll"),  # unset -> default poll
            ("poll", "poll"),
            ("redis", "redis"),
            ("REDIS", "redis"),  # case-insensitive
            (" redis ", "redis"),  # trimmed
            ("rabbitmq", "poll"),  # unknown -> safe default
            ("", "poll"),
        ],
    )
    def test_flag_parsing(self, monkeypatch, raw, expected):
        if raw is None:
            monkeypatch.delenv("PG_RESULT_SIGNAL_BACKEND", raising=False)
        else:
            monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", raw)
        assert _signal_backend() == expected


class TestWaitRouting:
    def test_poll_mode_uses_poll_path_not_redis(self, monkeypatch):
        """Default (poll) must never touch Redis and must use the backoff poll."""
        monkeypatch.delenv("PG_RESULT_SIGNAL_BACKEND", raising=False)
        rb = _backend_with_get_result(_ROW)
        # If the redis path were taken, this would blow up the test.
        rb._wait_via_redis = MagicMock(side_effect=AssertionError("took redis path"))  # type: ignore[method-assign]
        redis_spy = MagicMock(side_effect=AssertionError("built a redis client"))
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", redis_spy)

        assert rb.wait_for_result("k", timeout=1.0) == _ROW
        redis_spy.assert_not_called()

    def test_redis_mode_uses_redis_path(self, monkeypatch):
        monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", "redis")
        rb = _backend_with_get_result(_ROW)
        rb._wait_via_redis = MagicMock(return_value=_ROW)  # type: ignore[method-assign]
        assert rb.wait_for_result("k", timeout=1.0) == _ROW
        rb._wait_via_redis.assert_called_once()


class TestWaitViaRedis:
    def test_immediate_check_closes_publish_before_wait_race(self, monkeypatch):
        """Result already committed before we wait -> return WITHOUT a BLPOP."""
        monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", "redis")
        client = MagicMock()
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: client)
        rb = _backend_with_get_result(_ROW)  # first get_result already has the row

        assert rb.wait_for_result("k", timeout=5.0) == _ROW
        client.blpop.assert_not_called()  # never had to block

    def test_blpop_wake_then_authoritative_get(self, monkeypatch):
        monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", "redis")
        client = MagicMock()
        client.blpop.return_value = (_ready_key("k"), b"1")  # token arrived
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: client)
        # 1st get_result: not ready (race check); 2nd (post-BLPOP): the row.
        rb = _backend_with_get_result([None, _ROW])

        assert rb.wait_for_result("k", timeout=5.0) == _ROW
        client.blpop.assert_called_once()

    def test_redis_unavailable_degrades_to_poll(self, monkeypatch):
        """No Redis client -> behave exactly like poll mode (still returns)."""
        monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", "redis")
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: None)
        rb = _backend_with_get_result([None, _ROW])  # race-check None, poll finds it
        assert rb.wait_for_result("k", timeout=5.0) == _ROW

    def test_blpop_error_degrades_to_poll(self, monkeypatch):
        """A Redis blip mid-wait must not fail the wait — fall back to poll."""
        monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", "redis")
        client = MagicMock()
        client.blpop.side_effect = RuntimeError("redis down")
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: client)
        # race-check None -> BLPOP raises -> poll path finds it.
        rb = _backend_with_get_result([None, _ROW])
        assert rb.wait_for_result("k", timeout=5.0) == _ROW

    def test_timeout_returns_none(self, monkeypatch):
        monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", "redis")
        client = MagicMock()
        client.blpop.return_value = None  # BLPOP timed out, no token
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: client)
        rb = _backend_with_get_result(None)  # never ready
        assert rb.wait_for_result("k", timeout=0.05) is None


class TestStoreSignals:
    def test_store_signals_in_redis_mode(self, monkeypatch):
        monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", "redis")
        signalled = MagicMock()
        monkeypatch.setattr(rb_mod, "_signal_ready", signalled)
        rb = PgResultBackend()
        rb._store_with_reconnect = MagicMock()  # skip the DB write  # type: ignore[method-assign]

        rb.store_result("task-123", result={"ok": True})
        signalled.assert_called_once_with("task-123")

    def test_store_does_not_signal_in_poll_mode(self, monkeypatch):
        monkeypatch.delenv("PG_RESULT_SIGNAL_BACKEND", raising=False)
        signalled = MagicMock()
        monkeypatch.setattr(rb_mod, "_signal_ready", signalled)
        rb = PgResultBackend()
        rb._store_with_reconnect = MagicMock()  # type: ignore[method-assign]

        rb.store_result("task-123", result={"ok": True})
        signalled.assert_not_called()


class TestSignalReady:
    def test_signal_sends_only_the_key_no_payload(self, monkeypatch):
        client = MagicMock()
        pipe = client.pipeline.return_value
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: client)

        _signal_ready("task-abc")

        # Keyed by task_id only; value is a constant marker, never the result.
        pipe.rpush.assert_called_once_with(_ready_key("task-abc"), b"1")
        pipe.expire.assert_called_once()
        pipe.execute.assert_called_once()

    def test_signal_never_raises_on_redis_error(self, monkeypatch):
        client = MagicMock()
        client.pipeline.return_value.execute.side_effect = RuntimeError("redis down")
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: client)
        # Must swallow — the result is already durably committed.
        _signal_ready("task-abc")

    def test_signal_noop_when_no_client(self, monkeypatch):
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: None)
        _signal_ready("task-abc")  # no raise, no-op


class TestRedisRoundTripRealInfra:
    """End-to-end against REAL Redis + Postgres (skips if either is unreachable):
    a waiter on its OWN connection BLPOPs the token that store_result RPUSHes from
    another connection, then reads the committed row. Exercises the actual live path
    the unit tests stub out."""

    @pytest.fixture
    def real_redis(self):
        redis = pytest.importorskip("redis")
        client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        try:
            client.ping()
        except Exception:
            pytest.skip("Redis not reachable on localhost:6379")
        yield client
        for k in client.scan_iter("pg_result:ready:pgsig-*"):
            client.delete(k)

    def test_signal_roundtrip_cross_connection(self, monkeypatch, pg_conn, real_redis):
        monkeypatch.setenv("PG_RESULT_SIGNAL_BACKEND", "redis")
        monkeypatch.setattr(rb_mod, "_get_result_redis_client", lambda: real_redis)
        # The waiter opens its OWN connection (owned, so _wait_via_redis can
        # close+reopen it across BLPOP). Point those reconnects at the test DB
        # (the same TEST_DB_ prefix the fixture uses), not the default DB_ prefix.
        monkeypatch.setattr(
            rb_mod,
            "create_pg_connection",
            lambda *a, **k: create_pg_connection(env_prefix="TEST_DB_"),
        )
        key = f"pgsig-{uuid.uuid4()}"
        out: dict = {}

        def _wait():
            with PgResultBackend() as waiter:  # owns its own PG connection
                out["row"] = waiter.wait_for_result(key, timeout=10.0)

        t = threading.Thread(target=_wait)
        t.start()
        try:
            time.sleep(0.5)  # let the waiter reach BLPOP (token not yet pushed)
            # Store from a DIFFERENT connection -> commits row + RPUSHes the token.
            PgResultBackend(conn=pg_conn).store_result(key, result={"ok": True})
            t.join(timeout=12.0)
            assert not t.is_alive(), "waiter did not wake"
            assert out["row"] is not None
            assert out["row"]["status"] == "completed"
            assert out["row"]["result"] == {"ok": True}
        finally:
            t.join(timeout=1.0)
            with pg_conn.cursor() as cur:
                cur.execute("DELETE FROM pg_task_result WHERE task_id = %s", (key,))
            pg_conn.commit()
