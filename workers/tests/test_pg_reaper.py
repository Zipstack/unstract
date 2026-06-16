"""Tests for the PG-queue reaper (:mod:`queue_backend.pg_queue.reaper`).

Layers:

1. **Env / construction** — no DB (``reaper_interval_from_env``, the
   interval-shorter-than-lease guard).
2. **Leadership gating** — a fake lease + a patched sweep, no DB: recovery runs
   only while leader; a lost lease steps the reaper down; it re-acquires a later
   cycle; the lease is released on shutdown; ``run`` swallows a tick error.
3. **Connection handling** — mocked: a failed sweep rolls back + discards the
   owned connection; an injected connection is never swapped; the SQL contract.
4. **Barrier-orphan sweep** — real Postgres: only rows past ``expires_at`` are
   reclaimed; fresh barriers are left intact.
"""

from __future__ import annotations

import os
import threading
import time
from unittest.mock import MagicMock, patch

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
        assert reaper_interval_from_env() == pytest.approx(5.0)

    def test_overridable(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_REAPER_INTERVAL_SECONDS", "2.5")
        assert reaper_interval_from_env() == pytest.approx(2.5)

    @pytest.mark.parametrize("bad", ["0", "-1", "abc"])
    def test_invalid_raises(self, monkeypatch, bad):
        monkeypatch.setenv("WORKER_PG_REAPER_INTERVAL_SECONDS", bad)
        with pytest.raises(ValueError):
            reaper_interval_from_env()


class _FakeLease:
    """Duck-typed LeaderLease. ``acquires``/``renews`` accept a bool (constant)
    or a list (one outcome popped per call, then ``False``).
    """

    def __init__(self, *, acquires=True, renews=True, lease_seconds=10):
        self._acquires = acquires
        self._renews = renews
        self.lease_seconds = lease_seconds
        self.worker_id = "fake"
        self.released = False
        self.acquire_calls = 0
        self.renew_calls = 0

    @staticmethod
    def _next(val):
        if isinstance(val, list):
            return val.pop(0) if val else False
        return val

    def try_acquire(self):
        self.acquire_calls += 1
        return self._next(self._acquires)

    def renew(self):
        self.renew_calls += 1
        return self._next(self._renews)

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
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        with patch.object(
            reaper_mod, "sweep_expired_barriers", return_value=["x"]
        ) as sweep:
            outcome = reaper.tick()  # acquires leadership → sweeps
        assert outcome.was_leader is True
        assert outcome.reclaimed == 1
        assert reaper.is_leader is True
        sweep.assert_called_once()

    def test_standby_does_not_sweep(self):
        reaper = self._reaper(_FakeLease(acquires=False))  # can't get the lease
        with patch.object(reaper_mod, "sweep_expired_barriers") as sweep:
            outcome = reaper.tick()
        assert outcome == (False, 0)
        assert reaper.is_leader is False
        sweep.assert_not_called()

    def test_steps_down_when_renew_fails(self):
        # tick 1 acquires; tick 2 renew fails → step down, acquire also fails →
        # standby. Driven through ticks, no private-flag poking.
        reaper = self._reaper(_FakeLease(acquires=[True, False], renews=[False]))
        with patch.object(reaper_mod, "sweep_expired_barriers", return_value=[]):
            assert reaper.tick().was_leader is True
            assert reaper.tick().was_leader is False
        assert reaper.is_leader is False

    def test_steps_down_then_reacquires(self):
        # leader → lose the lease one cycle → re-acquire the next and resume.
        reaper = self._reaper(_FakeLease(acquires=[True, False, True], renews=[False]))
        with patch.object(reaper_mod, "sweep_expired_barriers", return_value=[]):
            assert reaper.tick().was_leader is True  # acquired
            assert reaper.tick().was_leader is False  # renew failed → standby
            assert reaper.tick().was_leader is True  # re-acquired
        assert reaper.is_leader is True

    def test_renew_raising_steps_down(self):
        lease = _FakeLease(acquires=True, renews=True)
        reaper = self._reaper(lease)
        with patch.object(reaper_mod, "sweep_expired_barriers", return_value=[]):
            reaper.tick()  # becomes leader
        lease.renew = MagicMock(side_effect=psycopg2.OperationalError("boom"))
        with pytest.raises(psycopg2.OperationalError):
            reaper.tick()
        assert reaper.is_leader is False  # raised renew == stop acting

    def test_release_on_stop_when_leader(self):
        lease = _FakeLease(acquires=True, renews=True)
        reaper = self._reaper(lease)
        with patch.object(reaper_mod, "sweep_expired_barriers", return_value=[]):
            t = threading.Thread(target=reaper.run, kwargs={"install_signals": False})
            t.start()
            time.sleep(0.05)
            reaper.stop()
            t.join(timeout=5)
        assert not t.is_alive()
        assert lease.released is True

    def test_run_swallows_tick_exception(self):
        reaper = PgReaper(_FakeLease(), interval_seconds=0.01, sweep_conn=object())
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            reaper.stop()  # one cycle only
            raise RuntimeError("transient blip")

        with patch.object(reaper, "tick", side_effect=boom):
            with patch.object(reaper_mod.logger, "exception") as logexc:
                reaper.run(install_signals=False)  # must not propagate
        assert calls["n"] == 1
        logexc.assert_called_once()


# --- Layer 3: connection handling (mocked, no DB) ---


class TestSweepConnection:
    def test_sql_contract(self):
        cur = MagicMock()
        cur.fetchall.return_value = [("e1",), ("e2",)]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        assert sweep_expired_barriers(conn) == ["e1", "e2"]
        sql = cur.execute.call_args[0][0]
        assert "DELETE FROM pg_barrier_state" in sql
        assert "expires_at < now()" in sql
        assert "RETURNING execution_id" in sql
        conn.commit.assert_called_once()

    def test_rolls_back_on_error(self):
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("dead")
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        with pytest.raises(psycopg2.OperationalError):
            sweep_expired_barriers(conn)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_owned_conn_recreated_when_closed(self, monkeypatch):
        dead = MagicMock(closed=True)
        fresh = MagicMock(closed=False)
        factory = MagicMock(side_effect=[dead, fresh])
        monkeypatch.setattr(reaper_mod, "create_pg_connection", factory)
        reaper = PgReaper(_FakeLease(), interval_seconds=1)  # owns its conn
        assert reaper._get_sweep_conn() is dead
        assert reaper._get_sweep_conn() is fresh  # dead.closed → recreate
        assert factory.call_count == 2

    def test_injected_conn_never_swapped(self):
        injected = MagicMock(closed=True)  # even closed, it's the caller's
        reaper = PgReaper(_FakeLease(), interval_seconds=1, sweep_conn=injected)
        assert reaper._get_sweep_conn() is injected

    def test_failed_sweep_discards_owned_conn(self, monkeypatch):
        conn = MagicMock(closed=False)
        monkeypatch.setattr(
            reaper_mod, "create_pg_connection", MagicMock(return_value=conn)
        )
        reaper = PgReaper(_FakeLease(acquires=True, renews=True), interval_seconds=1)
        with patch.object(
            reaper_mod,
            "sweep_expired_barriers",
            side_effect=psycopg2.OperationalError("x"),
        ):
            with pytest.raises(psycopg2.OperationalError):
                reaper.tick()
        conn.close.assert_called_once()
        assert reaper._sweep_conn is None  # next tick reconnects


# --- Layer 4: barrier-orphan sweep (real Postgres) ---


def _new_conn():
    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    # Manual-commit — exactly as the production reaper opens it
    # (create_pg_connection default). NOT autocommit: that would make
    # sweep_expired_barriers' own commit() a no-op and its rollback unreachable,
    # so Layer 4 would test a different mode than the real reaper runs in.
    return create_pg_connection(env_prefix="TEST_DB_")


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
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pg_barrier_state")
    conn.commit()
    conn.close()


def _seed(conn, execution_id, *, expired):
    # created_at must precede expires_at (CheckConstraint
    # pg_barrier_expires_after_created). Commit so the seed is durable like a
    # real barrier row (written by PgBarrier in another transaction) — and so the
    # manual-commit sweep's own commit() is what persists the DELETE.
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
    conn.commit()


def _ids(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT execution_id FROM pg_barrier_state ORDER BY execution_id")
        rows = [r[0] for r in cur.fetchall()]
    conn.commit()  # end the read transaction (manual-commit conn)
    return rows


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
        outcome = reaper.tick()  # became leader and reclaimed the orphan
        assert outcome.was_leader is True
        assert outcome.reclaimed == 1
        assert _ids(barrier_conn) == []


# --- Entry point (the `python -m pg_queue_reaper` launch path) ---


class TestEntryPoint:
    def test_main_module_reexports_real_main(self):
        # The single point where `run-worker.sh reaper` / `python -m
        # pg_queue_reaper` either works or dies on ImportError. Pin that the
        # launcher module re-exports the real reaper main.
        import importlib

        from queue_backend.pg_queue.reaper import main as real_main

        module = importlib.import_module("pg_queue_reaper.__main__")
        assert module.main is real_main


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
