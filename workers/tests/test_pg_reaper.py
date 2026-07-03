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

import logging
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psycopg2
import pytest
from queue_backend.pg_queue import reaper as reaper_mod
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.pg_queue.reaper import (
    PgReaper,
    dedup_retention_from_env,
    reaper_interval_from_env,
    reaper_sweep_interval_from_env,
    recover_expired_barriers,
    sweep_expired_results,
    sweep_orphan_claims,
    sweep_orphan_dedup,
)
from queue_backend.pg_queue.schema import qualified


# The reaper's leader tick also runs the PG scheduler tick (②b). Its behaviour
# is covered in test_pg_scheduler.py; stub it here by default so the leadership /
# recovery / connection tests aren't coupled to a real schedule query on their
# dummy or barrier-only connections. Tests that assert the wiring opt in via the
# returned mock.
@pytest.fixture(autouse=True)
def stub_scheduler_tick(monkeypatch):
    mock = MagicMock(return_value=0)
    monkeypatch.setattr(reaper_mod, "dispatch_due_schedules", mock)
    return mock


# The leader tick also runs the retention sweep (UN-3610). Stub the two sweep
# helpers by default so the leadership / connection tests don't hit a real DELETE
# on their dummy connections; the SQL-contract tests import the real helpers
# directly (unaffected by this module-attribute patch), and the sweep-wiring tests
# opt in via the returned mocks.
@pytest.fixture(autouse=True)
def stub_retention_sweep(monkeypatch):
    results = MagicMock(return_value=0)
    dedup = MagicMock(return_value=0)
    claims = MagicMock(return_value=0)
    monkeypatch.setattr(reaper_mod, "sweep_expired_results", results)
    monkeypatch.setattr(reaper_mod, "sweep_orphan_dedup", dedup)
    monkeypatch.setattr(reaper_mod, "sweep_orphan_claims", claims)
    return SimpleNamespace(results=results, dedup=dedup, claims=claims)


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


class TestSweepEnv:
    def test_sweep_interval_default_and_override(self, monkeypatch):
        monkeypatch.delenv("WORKER_PG_REAPER_SWEEP_SECONDS", raising=False)
        assert reaper_sweep_interval_from_env() == pytest.approx(300.0)
        monkeypatch.setenv("WORKER_PG_REAPER_SWEEP_SECONDS", "30")
        assert reaper_sweep_interval_from_env() == pytest.approx(30.0)

    def test_dedup_retention_default_and_override(self, monkeypatch):
        monkeypatch.delenv("WORKER_PG_DEDUP_RETENTION_SECONDS", raising=False)
        assert dedup_retention_from_env() == 86400
        monkeypatch.setenv("WORKER_PG_DEDUP_RETENTION_SECONDS", "3600")
        assert dedup_retention_from_env() == 3600

    @pytest.mark.parametrize("bad", ["0", "-5", "abc"])
    def test_invalid_raises(self, monkeypatch, bad):
        monkeypatch.setenv("WORKER_PG_REAPER_SWEEP_SECONDS", bad)
        monkeypatch.setenv("WORKER_PG_DEDUP_RETENTION_SECONDS", bad)
        with pytest.raises(ValueError):
            reaper_sweep_interval_from_env()
        with pytest.raises(ValueError):
            dedup_retention_from_env()

    def test_cast_distinction_float_vs_int(self, monkeypatch):
        # sweep parses as float, dedup as int — the cast is load-bearing.
        monkeypatch.setenv("WORKER_PG_REAPER_SWEEP_SECONDS", "1.5")
        assert reaper_sweep_interval_from_env() == pytest.approx(1.5)
        monkeypatch.setenv("WORKER_PG_DEDUP_RETENTION_SECONDS", "1.5")
        # int("1.5") rejects the fractional value; the message names the real cause
        # ("cannot be parsed: …") rather than the misleading "is not a number".
        with pytest.raises(ValueError, match="cannot be parsed"):
            dedup_retention_from_env()


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

    def test_non_positive_sweep_interval_rejected(self):
        # An injected knob bypasses the env parser's guard → re-validated in __init__.
        with pytest.raises(ValueError, match="sweep_interval"):
            PgReaper(
                _FakeLease(),
                interval_seconds=1,
                sweep_interval_seconds=0,
                sweep_conn=object(),
            )

    def test_non_positive_dedup_retention_rejected(self):
        with pytest.raises(ValueError, match="dedup_retention"):
            PgReaper(
                _FakeLease(),
                interval_seconds=1,
                dedup_retention_seconds=0,
                sweep_conn=object(),
            )


# --- Layer 2: leadership gating (fake lease + patched sweep, no DB) ---


class TestLeadershipGating:
    def _reaper(self, lease):
        # Inject dummy sweep_conn + api_client so a tick doesn't build real ones;
        # recover_expired_barriers is patched in each test, so neither is used.
        return PgReaper(
            lease, interval_seconds=0.01, sweep_conn=object(), api_client=object()
        )

    def test_sweeps_when_leader(self):
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        with patch.object(
            reaper_mod, "recover_expired_barriers", return_value=["x"]
        ) as sweep:
            outcome = reaper.tick()  # acquires leadership → sweeps
        assert outcome.was_leader is True
        assert outcome.reclaimed == 1
        assert reaper.is_leader is True
        sweep.assert_called_once()

    def test_standby_does_not_sweep(self):
        reaper = self._reaper(_FakeLease(acquires=False))  # can't get the lease
        with patch.object(reaper_mod, "recover_expired_barriers") as sweep:
            outcome = reaper.tick()
        assert outcome == (False, 0)
        assert reaper.is_leader is False
        sweep.assert_not_called()

    def test_steps_down_when_renew_fails(self):
        # tick 1 acquires; tick 2 renew fails → step down, acquire also fails →
        # standby. Driven through ticks, no private-flag poking.
        reaper = self._reaper(_FakeLease(acquires=[True, False], renews=[False]))
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            assert reaper.tick().was_leader is True
            assert reaper.tick().was_leader is False
        assert reaper.is_leader is False

    def test_steps_down_then_reacquires(self):
        # leader → lose the lease one cycle → re-acquire the next and resume.
        reaper = self._reaper(_FakeLease(acquires=[True, False, True], renews=[False]))
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            assert reaper.tick().was_leader is True  # acquired
            assert reaper.tick().was_leader is False  # renew failed → standby
            assert reaper.tick().was_leader is True  # re-acquired
        assert reaper.is_leader is True

    def test_renew_raising_steps_down(self):
        lease = _FakeLease(acquires=True, renews=True)
        reaper = self._reaper(lease)
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            reaper.tick()  # becomes leader
        lease.renew = MagicMock(side_effect=psycopg2.OperationalError("boom"))
        with pytest.raises(psycopg2.OperationalError):
            reaper.tick()
        assert reaper.is_leader is False  # raised renew == stop acting

    def test_release_on_stop_when_leader(self):
        lease = _FakeLease(acquires=True, renews=True)
        reaper = self._reaper(lease)
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
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


class TestSchedulerTick:
    """The orchestrator's second job: the leader (and only the leader) runs the
    PG scheduler tick each cycle. Scheduling behaviour itself is in
    test_pg_scheduler.py; here we only assert the wiring + leader gating.
    """

    def _reaper(self, lease):
        return PgReaper(
            lease, interval_seconds=0.01, sweep_conn=object(), api_client=object()
        )

    def test_leader_runs_scheduler(self, stub_scheduler_tick):
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            reaper.tick()
        stub_scheduler_tick.assert_called_once()

    def test_standby_does_not_run_scheduler(self, stub_scheduler_tick):
        reaper = self._reaper(_FakeLease(acquires=False))
        with patch.object(reaper_mod, "recover_expired_barriers"):
            reaper.tick()
        stub_scheduler_tick.assert_not_called()

    def test_scheduler_runs_after_recovery(self, stub_scheduler_tick):
        # Recovery is the safety net — it must run before scheduling so a
        # scheduler error can't starve it. Assert ordering via a shared call log.
        order = []
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        stub_scheduler_tick.side_effect = lambda *_: order.append("schedule")
        with patch.object(
            reaper_mod,
            "recover_expired_barriers",
            side_effect=lambda *_, **__: order.append("recover") or [],
        ):
            reaper.tick()
        assert order == ["recover", "schedule"]

    def test_scheduler_error_discards_owned_conn(self, stub_scheduler_tick):
        # A scheduler DB error must propagate (run() catches + continues) AND
        # discard the owned sweep conn — same posture as a failed recovery.
        # sweep_conn=None → owned; api_client=object() so _get_api_client doesn't
        # build a real one (both are evaluated to call the patched recovery).
        reaper = PgReaper(
            _FakeLease(acquires=True, renews=True),
            interval_seconds=0.01,
            api_client=object(),
        )
        owned = MagicMock()
        owned.closed = False  # so _get_sweep_conn returns it, doesn't reconnect
        reaper._sweep_conn = owned
        stub_scheduler_tick.side_effect = psycopg2.OperationalError("db gone")
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            with pytest.raises(psycopg2.OperationalError):
                reaper.tick()
        assert reaper._sweep_conn is None  # discarded


class TestRetentionSweepSql:
    """The sweep helpers' SQL contract (mock cursor, no DB). These call the real
    helpers (imported at module load), unaffected by the autouse stub which patches
    the module attribute the reaper looks up at call time.
    """

    @staticmethod
    def _conn_cur(rowcount):
        cur = MagicMock()
        cur.rowcount = rowcount
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        return conn, cur

    def test_sweep_expired_results_sql(self):
        conn, cur = self._conn_cur(3)
        assert sweep_expired_results(conn) == 3
        sql = cur.execute.call_args[0][0]
        assert (
            f"DELETE FROM {qualified('pg_task_result')}" in sql
            and "expires_at <= now()" in sql
        )
        conn.commit.assert_called_once()

    def test_sweep_orphan_dedup_sql(self):
        conn, cur = self._conn_cur(2)
        assert sweep_orphan_dedup(conn, 999) == 2
        args = cur.execute.call_args[0]
        assert f"DELETE FROM {qualified('pg_batch_dedup')}" in args[0]
        assert "created_at <= now() - make_interval" in args[0]
        assert args[1] == (999,)  # the retention param is bound, not interpolated
        conn.commit.assert_called_once()

    @pytest.mark.parametrize(
        "sweep",
        [
            lambda conn: sweep_expired_results(conn),
            lambda conn: sweep_orphan_dedup(conn, 60),
        ],
        ids=["expired_results", "orphan_dedup"],
    )
    def test_sweep_rolls_back_on_error(self, sweep):
        # Both helpers have their own try/except/rollback — exercise each.
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("dead")
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        with pytest.raises(psycopg2.OperationalError):
            sweep(conn)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_rollback_failure_is_logged_and_original_error_raised(self, caplog):
        # If rollback itself raises, surface it (don't swallow) but still propagate
        # the ORIGINAL DELETE error, not the rollback's.
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("dead")
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        conn.rollback.side_effect = psycopg2.InterfaceError("conn dead")
        with caplog.at_level(logging.WARNING, logger="queue_backend.pg_queue.reaper"):
            with pytest.raises(psycopg2.OperationalError):
                sweep_expired_results(conn)
        assert "rollback after a failed pg_task_result sweep also failed" in caplog.text


class TestRetentionSweepTick:
    """The sweep runs leader-only, after recovery + schedule, cadence-gated."""

    def _reaper(self, lease, **kw):
        kw.setdefault("sweep_interval_seconds", 300)
        kw.setdefault("dedup_retention_seconds", 86400)
        return PgReaper(
            lease, interval_seconds=0.01, sweep_conn=object(), api_client=object(), **kw
        )

    def test_leader_sweeps(self, stub_retention_sweep):
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        conn = reaper._sweep_conn  # capture once (don't re-fetch in the assertion)
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            reaper.tick()
        stub_retention_sweep.results.assert_called_once_with(conn)
        stub_retention_sweep.dedup.assert_called_once_with(conn, 86400)
        # Orphan-claim sweep (UN-3679) is wired with the api client + stuck-timeout
        # (+ the metrics exporter, so claim outcomes surface as counters).
        stub_retention_sweep.claims.assert_called_once_with(
            conn,
            reaper._get_api_client(),
            reaper._stuck_timeout_seconds,
            metrics=reaper.metrics,
        )

    def test_standby_does_not_sweep(self, stub_retention_sweep):
        reaper = self._reaper(_FakeLease(acquires=False))
        with patch.object(reaper_mod, "recover_expired_barriers"):
            reaper.tick()
        stub_retention_sweep.results.assert_not_called()
        stub_retention_sweep.dedup.assert_not_called()

    def test_cadence_gates_repeat_within_interval(self, stub_retention_sweep):
        # Two leader ticks well within the 300s interval → swept once, not twice.
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            reaper.tick()
            reaper.tick()
        assert stub_retention_sweep.results.call_count == 1
        assert stub_retention_sweep.dedup.call_count == 1

    def test_runs_after_recovery_and_schedule(
        self, stub_scheduler_tick, stub_retention_sweep
    ):
        order = []
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        stub_scheduler_tick.side_effect = lambda *_: order.append("schedule")
        stub_retention_sweep.results.side_effect = lambda *_: order.append("sweep") or 0
        with patch.object(
            reaper_mod,
            "recover_expired_barriers",
            side_effect=lambda *_, **__: order.append("recover") or [],
        ):
            reaper.tick()
        assert order == ["recover", "schedule", "sweep"]

    def test_one_sweep_failing_does_not_starve_the_other(
        self, stub_retention_sweep, caplog
    ):
        # [High] independence: a failing pg_task_result sweep must NOT skip the
        # pg_batch_dedup sweep, must NOT propagate (cleanup mustn't fail the tick),
        # and must discard the owned conn so the sibling reconnects.
        reaper = PgReaper(
            _FakeLease(acquires=True, renews=True),
            interval_seconds=0.01,
            sweep_interval_seconds=300,
            api_client=object(),
        )
        owned = MagicMock(closed=False)
        reaper._sweep_conn = owned
        stub_retention_sweep.results.side_effect = psycopg2.OperationalError("db gone")
        with (
            patch.object(
                reaper_mod, "create_pg_connection", return_value=MagicMock(closed=False)
            ) as reconnect,
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.reaper"),
        ):
            reaper.tick()  # must NOT raise
        stub_retention_sweep.results.assert_called_once()  # attempted + failed
        stub_retention_sweep.dedup.assert_called_once()  # sibling still ran
        reconnect.assert_called_once()  # reconnected after the discard
        assert "retention sweep of pg_task_result failed (1 consecutive)" in caplog.text

    def test_failing_sweep_still_advances_cadence(self, stub_retention_sweep):
        # The stamp is advanced before the sweep, so a failure waits one interval
        # before retry (no DB hammering) — a second immediate tick is gated out.
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        stub_retention_sweep.results.side_effect = RuntimeError("boom")
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            reaper.tick()
            reaper.tick()
        assert stub_retention_sweep.results.call_count == 1  # not retried immediately

    def test_logs_counts_only_when_rows_deleted(self, stub_retention_sweep, caplog):
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        stub_retention_sweep.results.return_value = 0
        stub_retention_sweep.dedup.return_value = 4  # one non-zero → still logs
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            caplog.at_level(logging.INFO, logger="queue_backend.pg_queue.reaper"),
        ):
            reaper.tick()
        assert (
            "deleted 0 pg_task_result + 4 pg_batch_dedup + 0 pg_orchestration_claim "
            "row(s)" in caplog.text
        )

    def test_no_log_when_nothing_deleted(self, stub_retention_sweep, caplog):
        reaper = self._reaper(_FakeLease(acquires=True, renews=True))
        # both stubs default to return_value=0
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            caplog.at_level(logging.INFO, logger="queue_backend.pg_queue.reaper"),
        ):
            reaper.tick()
        assert "retention sweep deleted" not in caplog.text


# --- Layer 3: connection handling (mocked, no DB) ---


class _FakeApiClient:
    """Models the real ``InternalAPIClient`` contract the reaper depends on.

    ``get_workflow_execution`` returns a response with ``success``/``status``
    (the real client returns ``success=False`` on any error instead of raising);
    ``fail_read`` models that. ``fail_update`` makes the ERROR-mark raise (the
    real ``update_*`` does raise). ``fail_update_for`` fails only specific ids.
    """

    def __init__(
        self,
        status="EXECUTING",
        *,
        fail_read=False,
        fail_update=False,
        fail_update_for=None,
        update_success=True,
        on_get=None,
    ):
        self._status = status
        self._fail_read = fail_read
        self._fail_update = fail_update
        self._fail_update_for = set(fail_update_for or [])
        # NON-raising failure: the real update client returns an APIResponse and can
        # report success=False rather than raising (like the read path).
        self._update_success = update_success
        self._on_get = on_get  # side-effect hook (e.g. re-arm the row mid-recovery)
        self.get_calls: list = []
        self.update_calls: list = []

    def get_workflow_execution(
        self, execution_id, organization_id=None, file_execution=True, **kw
    ):
        self.get_calls.append((execution_id, organization_id, file_execution))
        if self._on_get is not None:
            self._on_get(execution_id)
        if self._fail_read:
            return SimpleNamespace(success=False, status=None)  # real error contract
        return SimpleNamespace(success=True, status=self._status)

    def update_workflow_execution_status(
        self, execution_id, status, error_message=None, organization_id=None, **kw
    ):
        self.update_calls.append(
            SimpleNamespace(
                execution_id=execution_id,
                status=status,
                error_message=error_message,
                organization_id=organization_id,
                cascade_terminal_files=kw.get("cascade_terminal_files", False),
            )
        )
        if self._fail_update or execution_id in self._fail_update_for:
            raise RuntimeError("api down")
        return SimpleNamespace(success=self._update_success)


class TestRecoverConnection:
    def test_select_sql_contract(self):
        cur = MagicMock()
        cur.fetchall.return_value = []  # nothing expired
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        api = MagicMock()
        assert recover_expired_barriers(conn, api) == []
        sql = cur.execute.call_args[0][0]
        assert "SELECT" in sql and "pg_barrier_state" in sql
        assert "organization_id" in sql and "remaining" in sql
        assert "expires_at < now()" in sql
        conn.commit.assert_called_once()
        api.update_workflow_execution_status.assert_not_called()

    def test_rolls_back_on_select_error(self):
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("dead")
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        with pytest.raises(psycopg2.OperationalError):
            recover_expired_barriers(conn, MagicMock())
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
        reaper = PgReaper(
            _FakeLease(acquires=True, renews=True),
            interval_seconds=1,
            api_client=object(),  # injected so tick() doesn't build a real client
        )
        with patch.object(
            reaper_mod,
            "recover_expired_barriers",
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
    # (create_pg_connection default). NOT autocommit: that would make the
    # recover_expired_barriers commit a no-op and its rollback unreachable, so
    # Layer 4 would test a different mode than the real reaper runs in.
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
        cur.execute("DELETE FROM pg_batch_dedup")
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pg_barrier_state")
        cur.execute("DELETE FROM pg_batch_dedup")
    conn.commit()
    conn.close()


def _seed(
    conn,
    execution_id,
    *,
    expired,
    organization_id="org-1",
    remaining=1,
    last_progress="now()",
):
    # created_at must precede expires_at (CheckConstraint
    # pg_barrier_expires_after_created). Commit so the seed is durable like a
    # real barrier row (written by PgBarrier in another transaction) — and so the
    # manual-commit recovery's own commit is what persists the DELETE.
    # ``expired`` sets the absolute expires_at cap past/future; ``last_progress`` is
    # a raw SQL expr (default "now()" = fresh) so a test can seed a STALE
    # last_progress_at to exercise the fast (per-progress) stuck path independently.
    created_sql, expires_sql = (
        ("now() - interval '2 hours'", "now() - interval '1 hour'")
        if expired
        else ("now()", "now() + interval '6 hours'")
    )
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pg_barrier_state "
            "(execution_id, organization_id, remaining, results, "
            " created_at, expires_at, last_progress_at) "
            f"VALUES (%s, %s, %s, '[]'::jsonb, {created_sql}, {expires_sql}, "
            f"{last_progress})",
            (execution_id, organization_id, remaining),
        )
    conn.commit()


def _ids(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT execution_id FROM pg_barrier_state ORDER BY execution_id")
        rows = [r[0] for r in cur.fetchall()]
    conn.commit()  # end the read transaction (manual-commit conn)
    return rows


def _dedup_count(conn, execution_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_batch_dedup WHERE execution_id = %s",
            (execution_id,),
        )
        n = cur.fetchone()[0]
    conn.commit()
    return n


class TestRecoverExpiredBarriers:
    def test_recovers_only_expired_marks_error_and_cleans_up(self, barrier_conn):
        _seed(barrier_conn, "exp-1", expired=True, remaining=2)
        _seed(barrier_conn, "fresh-1", expired=False)
        api = _FakeApiClient(status="EXECUTING")
        recovered = recover_expired_barriers(barrier_conn, api)
        assert recovered == ["exp-1"]
        (call,) = api.update_calls  # exactly one execution marked
        assert call.execution_id == "exp-1"
        assert call.status == "ERROR"
        assert call.organization_id == "org-1"
        assert "never completed" in call.error_message  # remaining>0
        # Cascade the terminal status to the stranded execution's non-terminal
        # files (the b11ba2f3 fix) — else execution=ERROR while files stay EXECUTING.
        assert call.cascade_terminal_files is True
        assert _ids(barrier_conn) == ["fresh-1"]  # fresh barrier untouched

    def test_remaining_zero_uses_callback_stranded_message(self, barrier_conn):
        _seed(barrier_conn, "exp-0", expired=True, remaining=0)
        api = _FakeApiClient(status="EXECUTING")
        recover_expired_barriers(barrier_conn, api)
        (call,) = api.update_calls
        assert "callback never fired" in call.error_message

    def test_skips_already_terminal_execution(self, barrier_conn):
        # A remaining==0 expired row can belong to a COMPLETED exec whose row
        # delete failed — must NOT overwrite it to ERROR.
        _seed(barrier_conn, "exp-done", expired=True, remaining=0)
        api = _FakeApiClient(status="COMPLETED")
        recovered = recover_expired_barriers(barrier_conn, api)
        assert recovered == ["exp-done"]  # cleaned up
        assert api.update_calls == []  # no status overwrite
        assert _ids(barrier_conn) == []

    def test_org_missing_leaves_row_and_skips_mark(self, barrier_conn):
        # No org → can't call the org-scoped API; LEAVE the row (don't erase the
        # only recovery handle) and don't mark.
        _seed(barrier_conn, "exp-noorg", expired=True, organization_id="")
        api = _FakeApiClient()
        recovered = recover_expired_barriers(barrier_conn, api)
        assert recovered == []  # not recovered
        assert api.get_calls == [] and api.update_calls == []  # can't call org API
        assert _ids(barrier_conn) == ["exp-noorg"]  # row preserved for ops

    def test_failed_status_read_does_not_mark_and_retains_row(self, barrier_conn):
        # [Critical] the real client returns success=False (not raises) on a blip;
        # a failed read must NOT fall through to ERROR (would corrupt a COMPLETED
        # exec) — leave the row for the next sweep.
        _seed(barrier_conn, "exp-readfail", expired=True, remaining=0)
        api = _FakeApiClient(fail_read=True)
        recovered = recover_expired_barriers(barrier_conn, api)
        assert recovered == []
        assert api.update_calls == []  # never marked ERROR on an unconfirmed status
        assert _ids(barrier_conn) == ["exp-readfail"]  # retained for retry

    def test_status_read_passes_file_execution_false(self, barrier_conn):
        _seed(barrier_conn, "exp-fe", expired=True)
        api = _FakeApiClient(status="EXECUTING")
        recover_expired_barriers(barrier_conn, api)
        # Exactly one status read, recorded as exec-id / org / file_execution.
        # The reaper must skip the costly file-execution fetch it doesn't need.
        [(_exec_id, _org, file_execution)] = api.get_calls
        assert file_execution is False

    def test_api_failure_leaves_row_for_retry(self, barrier_conn):
        _seed(barrier_conn, "exp-fail", expired=True)
        api = _FakeApiClient(status="EXECUTING", fail_update=True)
        recovered = recover_expired_barriers(barrier_conn, api)
        assert recovered == []  # not recovered
        assert _ids(barrier_conn) == ["exp-fail"]  # row left for next sweep

    def test_one_failing_execution_does_not_block_others(self, barrier_conn):
        # Per-execution isolation: a mid-loop failure rolls back + the loop
        # continues; the others still recover.
        for eid in ("exp-a", "exp-bad", "exp-c"):
            _seed(barrier_conn, eid, expired=True)
        api = _FakeApiClient(status="EXECUTING", fail_update_for=["exp-bad"])
        recovered = recover_expired_barriers(barrier_conn, api)
        assert sorted(recovered) == ["exp-a", "exp-c"]  # the two good ones
        assert _ids(barrier_conn) == ["exp-bad"]  # only the failing row remains

    def test_rearmed_execution_is_not_marked_error(self, barrier_conn):
        # greptile #2070: if the same execution_id is re-enqueued (expires_at
        # reset to the future) between the sweep SELECT and the mark, the reaper
        # must NOT mark the freshly-running execution ERROR. Simulate the re-arm
        # via the status-read side-effect.
        _seed(barrier_conn, "exp-rearm", expired=True)

        def rearm(execution_id):
            with barrier_conn.cursor() as cur:
                cur.execute(
                    "UPDATE pg_barrier_state SET expires_at = now() + interval '6 hours' "
                    "WHERE execution_id = %s",
                    (execution_id,),
                )
            barrier_conn.commit()

        api = _FakeApiClient(status="EXECUTING", on_get=rearm)
        recovered = recover_expired_barriers(barrier_conn, api)
        assert recovered == []  # not recovered
        assert api.update_calls == []  # the live re-run was NOT marked ERROR
        assert _ids(barrier_conn) == ["exp-rearm"]  # re-armed row left intact

    def test_reaps_stale_last_progress_while_expires_at_future(self, barrier_conn):
        # THE headline path (UN-3661): a barrier is reaped via a stale
        # last_progress_at even though its absolute expires_at cap is still 6h in
        # the FUTURE (a crash mid-run → no 6h wait). And a *progressing* barrier
        # (fresh last_progress_at, same future cap) is NOT reaped — proving the
        # last_progress_at clause is load-bearing, not just the expires_at clause.
        _seed(
            barrier_conn,
            "stale-lp",
            expired=False,  # expires_at = now()+6h (future)
            remaining=2,
            last_progress="now() - interval '1 hour'",  # > 120s stuck window
        )
        _seed(barrier_conn, "fresh-lp", expired=False, last_progress="now()")
        api = _FakeApiClient(status="EXECUTING")
        recovered = recover_expired_barriers(barrier_conn, api, 120)  # stuck=120s
        assert recovered == ["stale-lp"]
        (call,) = api.update_calls
        assert call.execution_id == "stale-lp" and call.status == "ERROR"
        assert call.cascade_terminal_files is True
        assert _ids(barrier_conn) == ["fresh-lp"]  # progressing barrier untouched

    def test_progress_refresh_mid_recovery_aborts_the_mark(self, barrier_conn):
        # The re-arm race for the fast path: a decrement refreshes last_progress_at
        # to now() between the sweep SELECT and the mark → the barrier is no longer
        # stranded and the reaper must NOT mark its live run ERROR (mirrors the
        # expires_at re-arm test, but via last_progress_at).
        _seed(
            barrier_conn,
            "lp-rearm",
            expired=False,
            last_progress="now() - interval '1 hour'",
        )

        def refresh(execution_id):
            with barrier_conn.cursor() as cur:
                cur.execute(
                    "UPDATE pg_barrier_state SET last_progress_at = now() "
                    "WHERE execution_id = %s",
                    (execution_id,),
                )
            barrier_conn.commit()

        api = _FakeApiClient(status="EXECUTING", on_get=refresh)
        recovered = recover_expired_barriers(barrier_conn, api, 120)
        assert recovered == []  # progress refreshed → not stranded
        assert api.update_calls == []  # live run NOT marked ERROR
        assert _ids(barrier_conn) == ["lp-rearm"]  # row left for the new run

    def test_status_none_on_success_does_not_mark(self, barrier_conn):
        # A successful read with no status is anomalous — don't mark on it.
        _seed(barrier_conn, "exp-nostatus", expired=True)
        api = _FakeApiClient(status=None)  # success=True, status=None
        recovered = recover_expired_barriers(barrier_conn, api)
        assert recovered == []
        assert api.update_calls == []
        assert _ids(barrier_conn) == ["exp-nostatus"]  # left for next sweep

    def test_unsuccessful_status_write_does_not_delete_recovery_handle(
        self, barrier_conn
    ):
        # Defensive (mirrors the read path): if the status-update client ever
        # reports success=False WITHOUT raising, the reaper must NOT proceed to
        # DELETE the barrier row — that would erase the only recovery handle while
        # the execution stays non-terminal forever.
        _seed(barrier_conn, "exp-unsuccess", expired=True)
        api = _FakeApiClient(status="EXECUTING", update_success=False)
        recovered = recover_expired_barriers(barrier_conn, api)
        assert recovered == []  # the RuntimeError → row left for the next sweep
        assert _ids(barrier_conn) == ["exp-unsuccess"]  # recovery handle preserved

    def test_all_skipped_sweep_does_not_log_systemic_error(self, barrier_conn, caplog):
        # org-missing rows are benign skips, not failures — they must NOT trigger
        # the systemic "recovered NONE / API down" ERROR escalation.
        import logging

        _seed(barrier_conn, "exp-noorg", expired=True, organization_id="")
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.reaper"):
            recover_expired_barriers(barrier_conn, _FakeApiClient())
        assert not any("systemic" in r.message for r in caplog.records), (
            "all-skipped sweep should not escalate to a systemic-failure error"
        )

    def test_reclaims_dedup_markers(self, barrier_conn):
        _seed(barrier_conn, "exp-d", expired=True)
        with barrier_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pg_batch_dedup (execution_id, batch_index, created_at) "
                "VALUES ('exp-d', 0, now())"
            )
        barrier_conn.commit()
        recover_expired_barriers(barrier_conn, _FakeApiClient(status="EXECUTING"))
        assert _dedup_count(barrier_conn, "exp-d") == 0

    def test_noop_when_nothing_expired(self, barrier_conn):
        _seed(barrier_conn, "fresh-1", expired=False)
        assert recover_expired_barriers(barrier_conn, _FakeApiClient()) == []
        assert _ids(barrier_conn) == ["fresh-1"]

    def test_tick_recovers_via_real_conn(self, barrier_conn):
        _seed(barrier_conn, "exp-1", expired=True)
        reaper = PgReaper(
            _FakeLease(acquires=True, renews=True),
            interval_seconds=1,
            sweep_conn=barrier_conn,
            api_client=_FakeApiClient(status="EXECUTING"),
        )
        outcome = reaper.tick()  # became leader and recovered the orphan
        assert outcome.was_leader is True
        assert outcome.reclaimed == 1
        assert _ids(barrier_conn) == []


# --- Heartbeat + liveness probe ---


class TestHeartbeat:
    def test_fresh_after_init(self):
        reaper = PgReaper(_FakeLease(), interval_seconds=1, sweep_conn=object())
        assert reaper.seconds_since_last_tick() < 5
        assert reaper.is_tick_stale(1) is False

    def test_tick_refreshes_heartbeat(self):
        # Even a standby tick (no sweep) counts as loop progress.
        reaper = PgReaper(
            _FakeLease(acquires=False), interval_seconds=0.01, sweep_conn=object()
        )
        reaper._last_tick_monotonic = time.monotonic() - 100  # force stale
        assert reaper.is_tick_stale(1) is True
        reaper.tick()
        assert reaper.is_tick_stale(1) is False


def _http_get(server, path="/health"):
    import http.client
    import json as _json

    conn = http.client.HTTPConnection("127.0.0.1", server.bound_port, timeout=3)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, (_json.loads(raw) if raw else None)
    finally:
        conn.close()


class TestLivenessServer:
    def _server(self, reaper, *, stale_after=30.0):
        server = reaper_mod.ReaperLivenessServer(reaper, port=0, stale_after=stale_after)
        server.start()
        return server

    def test_fresh_returns_200(self):
        reaper = PgReaper(
            _FakeLease(acquires=False), interval_seconds=0.01, sweep_conn=object()
        )
        server = self._server(reaper)
        try:
            status, body = _http_get(server)
        finally:
            server.stop()
        assert status == 200
        assert body["status"] == "healthy"
        assert body["check"] == "pg_reaper_tick"
        assert body["is_leader"] is False

    def test_stale_returns_503(self):
        reaper = PgReaper(_FakeLease(), interval_seconds=0.01, sweep_conn=object())
        reaper._last_tick_monotonic = time.monotonic() - 100
        server = self._server(reaper, stale_after=1.0)
        try:
            status, body = _http_get(server)
        finally:
            server.stop()
        assert status == 503
        assert body["status"] == "unhealthy"

    def test_is_leader_reflected(self):
        reaper = PgReaper(
            _FakeLease(acquires=True, renews=True),
            interval_seconds=0.01,
            sweep_conn=object(),
        )
        with patch.object(reaper_mod, "recover_expired_barriers", return_value=[]):
            reaper.tick()  # becomes leader
        server = self._server(reaper)
        try:
            _, body = _http_get(server)
        finally:
            server.stop()
        assert body["is_leader"] is True

    def test_extra_status_cannot_clobber_core_fields(self):
        # A future extra_status_fn returning a reserved key must not corrupt the
        # core payload a monitor reads — core fields always win.
        from queue_backend.pg_queue.liveness import LivenessServer

        server = LivenessServer(
            freshness_fn=lambda: 0.0,
            stale_after=30,
            port=0,
            check_name="x",
            age_key="age",
            extra_status_fn=lambda: {"status": "HACKED", "check": "HACKED", "extra": 1},
        )
        server.start()
        try:
            status, body = _http_get(server)
        finally:
            server.stop()
        assert status == 200
        assert body["status"] == "healthy"  # core not clobbered
        assert body["check"] == "x"  # core not clobbered
        assert body["extra"] == 1  # non-reserved extra preserved

    def test_unknown_path_404(self):
        reaper = PgReaper(_FakeLease(), interval_seconds=1, sweep_conn=object())
        server = self._server(reaper)
        try:
            status, _ = _http_get(server, "/nope")
        finally:
            server.stop()
        assert status == 404

    def test_double_start_raises(self):
        reaper = PgReaper(_FakeLease(), interval_seconds=1, sweep_conn=object())
        server = self._server(reaper)
        try:
            with pytest.raises(RuntimeError):
                server.start()
        finally:
            server.stop()


class TestHealthEnv:
    def test_stale_default_is_thirty(self, monkeypatch):
        monkeypatch.delenv("WORKER_PG_REAPER_HEALTH_STALE_SECONDS", raising=False)
        assert reaper_mod._reaper_health_stale_from_env() == pytest.approx(30.0)

    def test_stale_overridable(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_REAPER_HEALTH_STALE_SECONDS", "10")
        assert reaper_mod._reaper_health_stale_from_env() == pytest.approx(10.0)

    @pytest.mark.parametrize("bad", ["0", "-1", "x"])
    def test_stale_invalid_raises(self, monkeypatch, bad):
        monkeypatch.setenv("WORKER_PG_REAPER_HEALTH_STALE_SECONDS", bad)
        with pytest.raises(ValueError):
            reaper_mod._reaper_health_stale_from_env()

    def test_health_server_disabled_when_no_port(self):
        reaper = PgReaper(_FakeLease(), interval_seconds=1, sweep_conn=object())
        assert (
            reaper_mod._maybe_start_health_server(reaper, port=None, stale_after=30)
            is None
        )

    def test_health_server_bind_failure_degrades_to_none(self, monkeypatch):
        # The documented graceful-degrade path: a bind failure must NOT stop the
        # reaper — log and run probe-less.
        reaper = PgReaper(_FakeLease(), interval_seconds=1, sweep_conn=object())
        monkeypatch.setattr(
            reaper_mod.ReaperLivenessServer,
            "start",
            MagicMock(side_effect=OSError("address already in use")),
        )
        with patch.object(reaper_mod.logger, "exception") as logexc:
            result = reaper_mod._maybe_start_health_server(
                reaper, port=12345, stale_after=30
            )
        assert result is None
        logexc.assert_called_once()

    def test_stale_after_non_positive_rejected(self):
        # Constructor re-validates (not only the env reader) — an always-503 probe
        # would crash-loop the pod.
        reaper = PgReaper(_FakeLease(), interval_seconds=1, sweep_conn=object())
        with pytest.raises(ValueError, match="stale_after"):
            reaper_mod.ReaperLivenessServer(reaper, port=0, stale_after=0)


class TestHealthPortEnv:
    def test_unset_is_none(self, monkeypatch):
        monkeypatch.delenv("WORKER_PG_REAPER_HEALTH_PORT", raising=False)
        assert reaper_mod._reaper_health_port_from_env() is None

    def test_empty_is_none(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_REAPER_HEALTH_PORT", "")
        assert reaper_mod._reaper_health_port_from_env() is None

    def test_valid_port(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_REAPER_HEALTH_PORT", "8086")
        assert reaper_mod._reaper_health_port_from_env() == 8086

    def test_non_int_raises_named(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_REAPER_HEALTH_PORT", "abc")
        with pytest.raises(ValueError, match="WORKER_PG_REAPER_HEALTH_PORT"):
            reaper_mod._reaper_health_port_from_env()

    def test_out_of_range_raises(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_REAPER_HEALTH_PORT", "99999")
        with pytest.raises(ValueError, match="out of range"):
            reaper_mod._reaper_health_port_from_env()


class TestMainWiring:
    def _patch_main(self, monkeypatch):
        # Don't open a DB connection or run the loop.
        monkeypatch.setattr(reaper_mod, "LeaderLease", lambda _wid: _FakeLease())
        monkeypatch.setattr(reaper_mod.PgReaper, "run", lambda self, **_kw: None)

    def test_wires_health_port_and_stops_on_exit(self, monkeypatch):
        self._patch_main(monkeypatch)
        monkeypatch.setenv("WORKER_PG_REAPER_HEALTH_PORT", "0")
        fake_health = MagicMock()
        captured: dict = {}

        def fake_start(_reaper, *, port, stale_after):
            captured["port"] = port
            return fake_health

        monkeypatch.setattr(reaper_mod, "_maybe_start_health_server", fake_start)
        reaper_mod.main()
        assert captured["port"] == 0  # parsed int reached the wiring
        fake_health.stop.assert_called_once()  # stopped in the finally

    def test_no_health_when_port_unset(self, monkeypatch):
        self._patch_main(monkeypatch)
        monkeypatch.delenv("WORKER_PG_REAPER_HEALTH_PORT", raising=False)
        captured: dict = {}

        def fake_start(_reaper, *, port, stale_after):
            captured["port"] = port
            return None

        monkeypatch.setattr(reaper_mod, "_maybe_start_health_server", fake_start)
        reaper_mod.main()  # must not raise even though health is None
        assert captured["port"] is None


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


# --- Layer 6: orphan orchestration-claim sweep (real Postgres, UN-3679) ---


@pytest.fixture
def claim_conn():
    try:
        conn = _new_conn()
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_orchestration_claim')")
        if cur.fetchone()[0] is None:
            conn.close()
            pytest.skip("pg_orchestration_claim migration not applied (run migrate)")
        cur.execute("DELETE FROM pg_orchestration_claim")
        cur.execute("DELETE FROM pg_barrier_state")
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pg_orchestration_claim")
        cur.execute("DELETE FROM pg_barrier_state")
    conn.commit()
    conn.close()


# Stuck-timeout used by these tests (seconds): claims OLDER than this are swept.
_CLAIM_STUCK = 60


def _seed_claim(conn, execution_id, *, old, organization_id="org-1"):
    # ``old`` seeds claimed_at past/within the stuck-timeout so a test exercises
    # the swept vs left-alone branches; committed so it's durable like a real claim.
    claimed_sql = "now() - interval '2 minutes'" if old else "now()"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pg_orchestration_claim "
            f"(execution_id, organization_id, claimed_at) VALUES (%s, %s, {claimed_sql})",
            (execution_id, organization_id),
        )
    conn.commit()


def _claim_ids(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT execution_id FROM pg_orchestration_claim ORDER BY 1")
        rows = [r[0] for r in cur.fetchall()]
    conn.commit()
    return rows


@pytest.mark.integration
class TestSweepOrphanClaims:
    def test_gc_terminal_tombstone(self, claim_conn):
        # A completed execution's tombstone (old, no barrier) → GC'd, no ERROR mark.
        _seed_claim(claim_conn, "done-1", old=True)
        api = _FakeApiClient(status="COMPLETED")
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 1
        assert _claim_ids(claim_conn) == []  # GC'd
        assert api.update_calls == []  # terminal → no mark

    def test_recovers_crash_window_marks_error(self, claim_conn):
        # Crash in the claim→arm window: old claim, no barrier, execution still
        # non-terminal → mark ERROR (+cascade) then delete the claim.
        _seed_claim(claim_conn, "strand-1", old=True)
        api = _FakeApiClient(status="EXECUTING")
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 1
        (call,) = api.update_calls
        assert call.execution_id == "strand-1"
        assert call.status == "ERROR"
        assert call.organization_id == "org-1"
        assert call.cascade_terminal_files is True
        assert "never armed" in call.error_message
        assert _claim_ids(claim_conn) == []  # deleted after the confirmed mark

    def test_leaves_young_claim(self, claim_conn):
        # A just-claimed live orchestration (claimed_at within the stuck-timeout)
        # must be left alone — not even a status read.
        _seed_claim(claim_conn, "live-1", old=False)
        api = _FakeApiClient(status="EXECUTING")
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 0
        assert api.get_calls == []  # not even inspected
        assert _claim_ids(claim_conn) == ["live-1"]

    def test_leaves_claim_with_armed_barrier(self, claim_conn):
        # A claim WITH a barrier row is a live/armed run — the barrier sweep owns
        # it; the claim sweep must skip it entirely (no status read).
        _seed_claim(claim_conn, "armed-1", old=True)
        _seed(claim_conn, "armed-1", expired=False)  # barrier row present
        api = _FakeApiClient(status="EXECUTING")
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 0
        assert api.get_calls == []
        assert _claim_ids(claim_conn) == ["armed-1"]

    def test_unconfirmed_mark_leaves_claim(self, claim_conn):
        # The status API reports success=False on the mark → do NOT delete the claim
        # (it's the only recovery handle); leave it for the next sweep.
        _seed_claim(claim_conn, "strand-2", old=True)
        api = _FakeApiClient(status="EXECUTING", update_success=False)
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 0
        assert len(api.update_calls) == 1  # mark attempted
        assert _claim_ids(claim_conn) == ["strand-2"]  # but kept

    def test_no_org_leaves_claim_without_api_call(self, claim_conn):
        # A claim with no org can't be recovered via the org-scoped API — leave it,
        # don't read status.
        _seed_claim(claim_conn, "no-org-1", old=True, organization_id="")
        api = _FakeApiClient(status="EXECUTING")
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 0
        assert api.get_calls == []
        assert _claim_ids(claim_conn) == ["no-org-1"]

    def test_one_failure_does_not_block_others(self, claim_conn):
        # A per-claim exception (here: a status read that raises) is caught and the
        # row left; the other claim is still swept in the same pass.
        _seed_claim(claim_conn, "aaa-done", old=True)
        _seed_claim(claim_conn, "zzz-boom", old=True)

        def _raise_for_boom(eid):
            if eid == "zzz-boom":
                raise RuntimeError("read boom")

        api = _FakeApiClient(status="COMPLETED", on_get=_raise_for_boom)
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 1  # aaa-done GC'd despite zzz-boom raising
        assert _claim_ids(claim_conn) == ["zzz-boom"]  # left for the next sweep

    def test_all_rows_failing_raises_systemic(self, claim_conn):
        # A non-empty sweep where EVERY row raises is systemic (API down) → raise so
        # _run_sweep records the consecutive-failure streak (a clean return would
        # reset it and hide that the recovery net is down).
        _seed_claim(claim_conn, "boom-1", old=True)
        _seed_claim(claim_conn, "boom-2", old=True)

        def _always_raise(_eid):
            raise RuntimeError("api down")

        api = _FakeApiClient(status="COMPLETED", on_get=_always_raise)
        with pytest.raises(RuntimeError, match="systemic"):
            sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert _claim_ids(claim_conn) == ["boom-1", "boom-2"]  # nothing removed

    def test_recheck_race_barrier_armed_leaves_claim(self, claim_conn):
        # A slow-but-live orchestration arms its barrier BETWEEN the sweep's SELECT
        # and the pre-mark re-check → the claim must NOT be marked ERROR.
        _seed_claim(claim_conn, "race-arm", old=True)

        def _arm_barrier(eid):
            if eid == "race-arm":
                _seed(claim_conn, eid, expired=False)  # barrier now exists

        api = _FakeApiClient(status="EXECUTING", on_get=_arm_barrier)
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 0
        assert api.update_calls == []  # re-check caught it → no ERROR mark
        assert _claim_ids(claim_conn) == ["race-arm"]  # left for the live run

    def test_delete_reguard_reclaim_leaves_fresh_claim(self, claim_conn):
        # Terminal → GC path, but the claim is released + re-claimed with a fresh
        # claimed_at between the SELECT and the DELETE → the re-guarded DELETE
        # matches 0 rows → the fresh claim survives and is NOT counted.
        _seed_claim(claim_conn, "race-gc", old=True)

        def _reclaim(eid):
            if eid == "race-gc":
                with claim_conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM pg_orchestration_claim WHERE execution_id = %s",
                        (eid,),
                    )
                    cur.execute(
                        "INSERT INTO pg_orchestration_claim "
                        "(execution_id, organization_id, claimed_at) "
                        "VALUES (%s, 'org-1', now())",
                        (eid,),
                    )
                claim_conn.commit()

        api = _FakeApiClient(status="COMPLETED", on_get=_reclaim)
        removed = sweep_orphan_claims(claim_conn, api, _CLAIM_STUCK)
        assert removed == 0  # 0-row delete → not counted
        assert _claim_ids(claim_conn) == ["race-gc"]  # the fresh claim survives


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
