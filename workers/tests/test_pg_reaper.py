"""Tests for the PG-queue reaper (:mod:`queue_backend.pg_queue.reaper`).

Three layers:

1. **Env / construction** — no DB (``reaper_interval_from_env``, the
   interval-shorter-than-lease guard).
2. **Leadership gating** — a fake lease + a patched sweep, no DB: recovery runs
   only while leader; a lost lease steps the reaper down; the lease is released
   on shutdown.
3. **Barrier-orphan sweep** — real Postgres: only rows past ``expires_at`` are
   reclaimed; fresh barriers are left intact.
"""

from __future__ import annotations

import os
import threading
import time
from unittest.mock import patch

import psycopg2
import pytest
from queue_backend.pg_queue import reaper as reaper_mod
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.pg_queue.reaper import (
    PgReaper,
    reaper_interval_from_env,
    sweep_expired_barriers,
)

# --- Layer 1: env + construction (no DB) ---


class TestIntervalEnv:
    def test_default_is_five_seconds(self, monkeypatch):
        monkeypatch.delenv("WORKER_PG_REAPER_INTERVAL_SECONDS", raising=False)
        assert reaper_interval_from_env() == 5.0

    def test_overridable(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_REAPER_INTERVAL_SECONDS", "2.5")
        assert reaper_interval_from_env() == 2.5

    @pytest.mark.parametrize("bad", ["0", "-1", "abc"])
    def test_invalid_raises(self, monkeypatch, bad):
        monkeypatch.setenv("WORKER_PG_REAPER_INTERVAL_SECONDS", bad)
        with pytest.raises(ValueError):
            reaper_interval_from_env()


class _FakeLease:
    """Stand-in for LeaderLease with scriptable acquire/renew outcomes."""

    def __init__(self, *, acquires=True, renews=True, lease_seconds=10):
        self._acquires = acquires
        self._renews = renews
        self.lease_seconds = lease_seconds
        self.worker_id = "fake"
        self.released = False
        self.acquire_calls = 0
        self.renew_calls = 0

    def try_acquire(self):
        self.acquire_calls += 1
        return self._acquires

    def renew(self):
        self.renew_calls += 1
        return self._renews

    def release(self):
        self.released = True


class TestConstruction:
    def test_interval_must_be_shorter_than_lease(self):
        with pytest.raises(ValueError, match="shorter than the lease"):
            PgReaper(_FakeLease(lease_seconds=5), interval_seconds=5, sweep_conn=object())

    def test_non_positive_interval_rejected(self):
        with pytest.raises(ValueError):
            PgReaper(_FakeLease(), interval_seconds=0, sweep_conn=object())

    def test_valid_interval_accepted(self):
        PgReaper(_FakeLease(lease_seconds=10), interval_seconds=3, sweep_conn=object())


# --- Layer 2: leadership gating (fake lease + patched sweep, no DB) ---


class TestLeadershipGating:
    def _reaper(self, lease):
        return PgReaper(lease, interval_seconds=0.01, sweep_conn=object())

    def test_sweeps_when_leader(self):
        lease = _FakeLease(acquires=True, renews=True)
        reaper = self._reaper(lease)
        with patch.object(
            reaper_mod, "sweep_expired_barriers", return_value=["x"]
        ) as sweep:
            assert reaper.tick() == 1  # acquired leadership → swept
        sweep.assert_called_once()

    def test_standby_does_not_sweep(self):
        lease = _FakeLease(acquires=False)  # can't get the lease
        reaper = self._reaper(lease)
        with patch.object(reaper_mod, "sweep_expired_barriers") as sweep:
            assert reaper.tick() == -1
        sweep.assert_not_called()

    def test_steps_down_when_renew_fails(self):
        # Already leader, but the lease was taken over → renew False → step down
        # and (acquires=False) stay standby; no sweep this cycle.
        lease = _FakeLease(acquires=False, renews=False)
        reaper = self._reaper(lease)
        reaper._is_leader = True
        with patch.object(reaper_mod, "sweep_expired_barriers") as sweep:
            assert reaper.tick() == -1
        assert reaper._is_leader is False
        sweep.assert_not_called()

    def test_release_on_stop_when_leader(self):
        lease = _FakeLease(acquires=True, renews=True)
        reaper = self._reaper(lease)
        with patch.object(reaper_mod, "sweep_expired_barriers", return_value=[]):
            t = threading.Thread(target=reaper.run, kwargs={"install_signals": False})
            t.start()
            time.sleep(0.05)  # let it acquire + tick a few times
            reaper.stop()
            t.join(timeout=5)
        assert not t.is_alive()
        assert lease.released is True


# --- Layer 3: barrier-orphan sweep (real Postgres) ---


def _new_conn():
    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    conn = create_pg_connection(env_prefix="TEST_DB_")
    conn.autocommit = True
    return conn


@pytest.fixture
def barrier_conn():
    try:
        conn = _new_conn()
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_barrier_state')")
        if cur.fetchone()[0] is None:
            conn.close()
            pytest.skip("pg_barrier_state migration not applied (run backend migrate)")
        cur.execute("DELETE FROM pg_barrier_state")
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pg_barrier_state")
    conn.close()


def _seed(conn, execution_id, *, expired):
    # expired → expires_at in the past; created_at must precede expires_at
    # (CheckConstraint pg_barrier_expires_after_created).
    with conn.cursor() as cur:
        if expired:
            cur.execute(
                "INSERT INTO pg_barrier_state "
                "(execution_id, remaining, results, created_at, expires_at) "
                "VALUES (%s, 1, '[]'::jsonb, now() - interval '2 hours', "
                "        now() - interval '1 hour')",
                (execution_id,),
            )
        else:
            cur.execute(
                "INSERT INTO pg_barrier_state "
                "(execution_id, remaining, results, created_at, expires_at) "
                "VALUES (%s, 1, '[]'::jsonb, now(), now() + interval '6 hours')",
                (execution_id,),
            )


def _ids(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT execution_id FROM pg_barrier_state ORDER BY execution_id")
        return [r[0] for r in cur.fetchall()]


class TestSweepExpiredBarriers:
    def test_reclaims_only_expired(self, barrier_conn):
        _seed(barrier_conn, "exp-1", expired=True)
        _seed(barrier_conn, "exp-2", expired=True)
        _seed(barrier_conn, "fresh-1", expired=False)
        reclaimed = sweep_expired_barriers(barrier_conn)
        assert sorted(reclaimed) == ["exp-1", "exp-2"]
        assert _ids(barrier_conn) == ["fresh-1"]  # fresh barrier untouched

    def test_noop_when_nothing_expired(self, barrier_conn):
        _seed(barrier_conn, "fresh-1", expired=False)
        assert sweep_expired_barriers(barrier_conn) == []
        assert _ids(barrier_conn) == ["fresh-1"]

    def test_tick_sweeps_via_real_conn(self, barrier_conn):
        _seed(barrier_conn, "exp-1", expired=True)
        reaper = PgReaper(
            _FakeLease(acquires=True, renews=True),
            interval_seconds=1,
            sweep_conn=barrier_conn,
        )
        assert reaper.tick() == 1  # became leader and reclaimed the orphan
        assert _ids(barrier_conn) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
