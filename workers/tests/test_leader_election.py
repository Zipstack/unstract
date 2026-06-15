"""Tests for :class:`queue_backend.pg_queue.leader_election.LeaderLease`.

Two layers:

1. **Env / construction** — no DB (``lease_seconds_from_env``, worker-id guard).
2. **Lease semantics** — real Postgres. Each ``LeaderLease`` is given its own
   autocommit connection so two instances genuinely race the single
   ``pg_orchestrator_lock`` row. Skips if Postgres is unreachable or the
   ``pg_orchestrator_lock`` migration is unapplied.

The two load-bearing correctness properties:
- concurrent ``try_acquire`` on a free lock → **exactly one** winner;
- ``renew`` returns ``False`` after a standby took over a stale lease (the
  signal that tells a stalled leader to stop acting).
"""

from __future__ import annotations

import contextlib
import os
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import psycopg2
import pytest
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.pg_queue.leader_election import (
    LeaderLease,
    default_worker_id,
    lease_seconds_from_env,
)

# --- Layer 1: env + construction (no DB) ---


class TestLeaseSecondsEnv:
    def test_default_is_ten_seconds(self, monkeypatch):
        monkeypatch.delenv("WORKER_PG_ORCHESTRATOR_LEASE_SECONDS", raising=False)
        assert lease_seconds_from_env() == 10

    def test_overridable(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_ORCHESTRATOR_LEASE_SECONDS", "30")
        assert lease_seconds_from_env() == 30

    @pytest.mark.parametrize("bad", ["0", "-5", "abc", "1.5"])
    def test_invalid_raises(self, monkeypatch, bad):
        monkeypatch.setenv("WORKER_PG_ORCHESTRATOR_LEASE_SECONDS", bad)
        with pytest.raises(ValueError):
            lease_seconds_from_env()


class TestConstruction:
    @pytest.mark.parametrize("bad", ["", "   "])
    def test_empty_worker_id_rejected(self, bad):
        with pytest.raises(ValueError, match="non-empty"):
            LeaderLease(bad, conn=object())  # conn unused — guard fires first

    def test_non_positive_lease_seconds_rejected(self):
        with pytest.raises(ValueError):
            LeaderLease("w1", lease_seconds=0, conn=object())

    def test_default_worker_id_shape_and_idempotent(self):
        default_worker_id.cache_clear()
        wid = default_worker_id()
        # host:pid:rand shape, three colon-separated parts.
        assert len(wid.split(":")) == 3
        # Idempotent within a process (lru_cache) — repeated calls match, so a
        # caller can pass it inline without drifting the worker id.
        assert default_worker_id() == wid
        default_worker_id.cache_clear()


# --- Layer 1b: connection recovery / ownership (mocked, no DB) ---


def _mock_conn(*, execute_exc=None, rollback_exc=None, fetch=(1,)):
    cur = MagicMock()
    if execute_exc is not None:
        cur.execute.side_effect = execute_exc
    cur.fetchone.return_value = fetch
    cur.rowcount = 1
    conn = MagicMock()
    conn.closed = 0
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    if rollback_exc is not None:
        conn.rollback.side_effect = rollback_exc
    return conn


_FACTORY_PATH = "queue_backend.pg_queue.leader_election.create_pg_connection"


class TestConnectionRecovery:
    """Owned vs injected recovery branches of ``_cursor`` — the load-bearing
    self-recovery the docstrings advertise (mirrors PgQueueClient's suite)."""

    def test_owned_conn_recovered_on_operational_error(self, monkeypatch):
        bad = _mock_conn(execute_exc=psycopg2.OperationalError("dead"))
        good = _mock_conn(fetch=(1,))
        factory = MagicMock(side_effect=[bad, good])
        monkeypatch.setattr(_FACTORY_PATH, factory)
        lease = LeaderLease("w")  # owns its connection (conn=None)
        with pytest.raises(psycopg2.OperationalError):
            lease.try_acquire()
        bad.rollback.assert_called_once()
        bad.close.assert_called_once()
        assert lease._conn is None  # dead owned handle dropped
        assert lease.try_acquire() is True  # next call reconnects to good
        assert factory.call_count == 2

    def test_owned_conn_recovered_when_rollback_fails(self, monkeypatch):
        # Non-Operational error whose rollback also fails → still treated dead.
        bad = _mock_conn(
            execute_exc=RuntimeError("boom"),
            rollback_exc=psycopg2.DatabaseError("socket gone"),
        )
        monkeypatch.setattr(_FACTORY_PATH, MagicMock(side_effect=[bad]))
        lease = LeaderLease("w")
        with pytest.raises(RuntimeError):
            lease.try_acquire()
        bad.close.assert_called_once()
        assert lease._conn is None

    def test_injected_conn_never_swapped_on_error(self):
        # The High finding: an injected (caller-owned) connection must NOT be
        # closed + silently replaced with a DB_-env one on a transient error.
        bad = _mock_conn(execute_exc=psycopg2.OperationalError("dead"))
        lease = LeaderLease("w", conn=bad)
        with pytest.raises(psycopg2.OperationalError):
            lease.try_acquire()
        bad.rollback.assert_called_once()
        bad.close.assert_not_called()
        assert lease._conn is bad  # caller's connection untouched


# --- Layer 2: lease semantics (real Postgres) ---


def _new_conn():
    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    conn = create_pg_connection(env_prefix="TEST_DB_")
    conn.autocommit = True
    return conn


@pytest.fixture
def lock_db():
    """Reset the single lock row to free before/after each test.

    Yields a helper connection (for assertions / ageing the lease); each
    ``LeaderLease`` under test gets its OWN connection so concurrency is real.
    Skips when Postgres is unreachable or the migration is unapplied.
    """
    try:
        conn = _new_conn()
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_orchestrator_lock')")
        if cur.fetchone()[0] is None:
            conn.close()
            pytest.skip(
                "pg_orchestrator_lock migration not applied (run backend migrate)"
            )
        # Ensure the singleton row exists and is free (the migration seeds it,
        # but reset defensively so tests are order-independent).
        cur.execute(
            "INSERT INTO pg_orchestrator_lock (id, leader, acquired_at) "
            "VALUES (1, '', now()) "
            "ON CONFLICT (id) DO UPDATE SET leader = '', acquired_at = now()"
        )
    extra_conns: list = []

    def make_lease(worker_id, **kw):
        c = _new_conn()
        extra_conns.append(c)
        return LeaderLease(worker_id, conn=c, **kw)

    yield SimpleNamespace(conn=conn, make_lease=make_lease)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pg_orchestrator_lock SET leader = '', acquired_at = now() "
            "WHERE id = 1"
        )
    for c in extra_conns:
        with contextlib.suppress(Exception):
            c.close()
    conn.close()


def _leader(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT leader FROM pg_orchestrator_lock WHERE id = 1")
        return cur.fetchone()[0]


def _age_lease(conn, seconds: int) -> None:
    """Push acquired_at into the past so the lease looks stale."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pg_orchestrator_lock "
            "SET acquired_at = now() - make_interval(secs => %s) WHERE id = 1",
            (seconds,),
        )


class TestLeaderLease:
    def test_acquire_on_free_lock_succeeds(self, lock_db):
        lease = lock_db.make_lease("w1")
        assert lease.try_acquire() is True
        assert _leader(lock_db.conn) == "w1"

    def test_second_acquirer_fails_while_fresh(self, lock_db):
        a = lock_db.make_lease("a")
        b = lock_db.make_lease("b")
        assert a.try_acquire() is True
        assert b.try_acquire() is False
        assert _leader(lock_db.conn) == "a"

    def test_stale_lease_allows_takeover(self, lock_db):
        a = lock_db.make_lease("a", lease_seconds=10)
        b = lock_db.make_lease("b", lease_seconds=10)
        assert a.try_acquire() is True
        _age_lease(lock_db.conn, 30)  # older than the 10s window
        assert b.try_acquire() is True
        assert _leader(lock_db.conn) == "b"

    def test_same_holder_reacquire_while_fresh_returns_false(self, lock_db):
        # The current holder can't re-acquire a fresh lease (the WHERE rejects
        # even the holder until it goes stale) — renew is the holder's path.
        a = lock_db.make_lease("a")
        assert a.try_acquire() is True
        assert a.try_acquire() is False
        assert a.renew() is True  # ...but renew keeps it
        assert _leader(lock_db.conn) == "a"

    def test_renew_keeps_leadership(self, lock_db):
        a = lock_db.make_lease("a")
        b = lock_db.make_lease("b")
        assert a.try_acquire() is True
        assert a.renew() is True
        assert b.try_acquire() is False  # still fresh after renew

    def test_renew_by_non_holder_returns_false(self, lock_db):
        a = lock_db.make_lease("a")
        b = lock_db.make_lease("b")
        assert a.try_acquire() is True
        assert b.renew() is False
        assert _leader(lock_db.conn) == "a"  # unchanged

    def test_renew_after_takeover_returns_false(self, lock_db):
        # The critical safety signal: a stalled leader learns it lost the lease.
        a = lock_db.make_lease("a", lease_seconds=10)
        b = lock_db.make_lease("b", lease_seconds=10)
        assert a.try_acquire() is True
        _age_lease(lock_db.conn, 30)
        assert b.try_acquire() is True  # standby takes over
        assert a.renew() is False  # original must stop acting

    def test_release_frees_immediately(self, lock_db):
        a = lock_db.make_lease("a")
        b = lock_db.make_lease("b")
        assert a.try_acquire() is True
        a.release()
        assert _leader(lock_db.conn) == ""
        assert b.try_acquire() is True  # no need to wait out the TTL

    def test_release_by_non_holder_is_noop(self, lock_db):
        a = lock_db.make_lease("a")
        b = lock_db.make_lease("b")
        assert a.try_acquire() is True
        b.release()  # b doesn't hold it
        assert _leader(lock_db.conn) == "a"  # a still leader
        assert a.renew() is True

    def test_release_after_takeover_is_noop(self, lock_db):
        # A stalled leader's late release must not wipe the standby that took
        # over ("a late release can't wipe the new holder").
        a = lock_db.make_lease("a", lease_seconds=10)
        b = lock_db.make_lease("b", lease_seconds=10)
        assert a.try_acquire() is True
        _age_lease(lock_db.conn, 30)
        assert b.try_acquire() is True  # standby took over
        a.release()  # late release from the deposed leader
        assert _leader(lock_db.conn) == "b"  # new holder intact

    def test_concurrent_acquire_exactly_one_wins(self, lock_db):
        # N candidates, each its own connection, race try_acquire on a free lock.
        # The row lock serialises the conditional UPDATE → exactly one RETURNING.
        results: dict[str, bool] = {}

        def run(label):
            lease = lock_db.make_lease(label)
            results[label] = lease.try_acquire()

        labels = [f"c{i}" for i in range(5)]
        threads = [threading.Thread(target=run, args=(x,)) for x in labels]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert all(not t.is_alive() for t in threads)
        assert sum(results.values()) == 1  # exactly one winner
        winner = next(label for label, won in results.items() if won)
        assert _leader(lock_db.conn) == winner


class TestSingleRowConstraint:
    def test_second_row_rejected(self, lock_db):
        with pytest.raises(psycopg2.errors.CheckViolation):
            with lock_db.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pg_orchestrator_lock (id, leader, acquired_at) "
                    "VALUES (2, '', now())"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
