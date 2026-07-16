"""Tests for the PG-queue consumer prefork supervisor (UN-3606).

DB-free / fork-free: the env knob, the ``_Fleet`` bookkeeping, the reap/restart
scheduling, the join+SIGKILL escalation and the fork/health guards are exercised in
isolation (``os.*`` mocked) so the suite stays fast and deterministic — no real
children, no worker bootstrap, no signals installed.
"""

import errno
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from pg_queue_consumer import supervisor as sup
from pg_queue_consumer.supervisor import (
    _CRASH_LOOP_THRESHOLD,
    _DEFAULT_SHUTDOWN_GRACE_SECONDS,
    _MAX_CONCURRENCY,
    _MIN_HEALTHY_UPTIME_SECONDS,
    _Fleet,
    _child_after_fork,
    _join_children,
    _reap_dead,
    _restart_due_children,
    _try_fork_child,
    _wait_for_exit,
    concurrency_from_env,
    shutdown_grace_from_env,
)

_MOD = "pg_queue_consumer.supervisor"
_ENV = "WORKER_PG_QUEUE_CONSUMER_CONCURRENCY"


_VT = "WORKER_PG_QUEUE_CONSUMER_VT_SECONDS"
_GRACE = "WORKER_PG_QUEUE_CONSUMER_SHUTDOWN_GRACE_SECONDS"


class TestShutdownGraceFromEnv:
    """UN-3695: the shutdown drain grace must track the consumer VT (not a hardcoded
    30s), so a SIGTERM drains an in-flight batch instead of SIGKILLing it mid-flight.
    """

    def test_unset_vt_and_override_defaults_to_fallback(self, monkeypatch):
        monkeypatch.delenv(_VT, raising=False)
        monkeypatch.delenv(_GRACE, raising=False)
        assert shutdown_grace_from_env() == pytest.approx(_DEFAULT_SHUTDOWN_GRACE_SECONDS)

    def test_tracks_vt_when_set(self, monkeypatch):
        # The fileproc chart sets VT=9060 → grace must follow it, not stay at 30.
        monkeypatch.delenv(_GRACE, raising=False)
        monkeypatch.setenv(_VT, "9060")
        assert shutdown_grace_from_env() == pytest.approx(9060.0)

    def test_vt_below_fallback_is_floored(self, monkeypatch):
        monkeypatch.delenv(_GRACE, raising=False)
        monkeypatch.setenv(_VT, "10")
        assert shutdown_grace_from_env() == pytest.approx(_DEFAULT_SHUTDOWN_GRACE_SECONDS)

    def test_explicit_override_wins_over_vt(self, monkeypatch):
        monkeypatch.setenv(_VT, "9060")
        monkeypatch.setenv(_GRACE, "120")
        assert shutdown_grace_from_env() == pytest.approx(120.0)

    def test_override_honoured_as_is_even_below_fallback(self, monkeypatch):
        # An explicit short dev drain is respected (not floored) — only the VT path floors.
        monkeypatch.delenv(_VT, raising=False)
        monkeypatch.setenv(_GRACE, "5")
        assert shutdown_grace_from_env() == pytest.approx(5.0)

    def test_negative_override_raises(self, monkeypatch):
        # A negative drain budget would collapse to 0 → SIGKILL with no drain (the
        # orphan bug this module prevents). Must fail fast, not silently.
        monkeypatch.setenv(_GRACE, "-5")
        with pytest.raises(ValueError, match="SHUTDOWN_GRACE_SECONDS"):
            shutdown_grace_from_env()

    def test_non_finite_override_raises(self, monkeypatch):
        # inf would make the join deadline now+inf → shutdown hangs until k8s
        # hard-kills the pod; nan collapses to 0. Reject both.
        monkeypatch.setenv(_GRACE, "inf")
        with pytest.raises(ValueError, match="finite"):
            shutdown_grace_from_env()

    def test_malformed_override_raises(self, monkeypatch):
        monkeypatch.setenv(_GRACE, "abc")
        with pytest.raises(ValueError, match="SHUTDOWN_GRACE_SECONDS"):
            shutdown_grace_from_env()

    def test_malformed_vt_raises(self, monkeypatch):
        # Fail-fast-at-startup contract: a bad VT surfaces the offending var name.
        monkeypatch.delenv(_GRACE, raising=False)
        monkeypatch.setenv(_VT, "9060s")
        with pytest.raises(ValueError, match="VT_SECONDS"):
            shutdown_grace_from_env()


class TestConcurrencyFromEnv:
    def test_unset_defaults_to_one(self, monkeypatch):
        monkeypatch.delenv(_ENV, raising=False)
        assert concurrency_from_env() == 1

    def test_empty_defaults_to_one(self, monkeypatch):
        monkeypatch.setenv(_ENV, "")
        assert concurrency_from_env() == 1

    def test_valid_value(self, monkeypatch):
        monkeypatch.setenv(_ENV, "4")
        assert concurrency_from_env() == 4

    def test_clamped_to_max(self, monkeypatch):
        monkeypatch.setenv(_ENV, str(_MAX_CONCURRENCY + 50))
        assert concurrency_from_env() == _MAX_CONCURRENCY

    @pytest.mark.parametrize("bad", ["0", "-3"])
    def test_below_one_raises(self, monkeypatch, bad):
        monkeypatch.setenv(_ENV, bad)
        with pytest.raises(ValueError, match=">= 1"):
            concurrency_from_env()

    def test_non_int_raises(self, monkeypatch):
        monkeypatch.setenv(_ENV, "abc")
        with pytest.raises(ValueError, match="Invalid"):
            concurrency_from_env()


class TestFleet:
    def test_record_and_reap_keep_structures_consistent(self):
        f = _Fleet(2)
        f.record_fork(0, 111)
        assert f.alive_items() == [(0, 111)] and f.alive_count() == 1
        uptime = f.reap(0)
        assert uptime >= 0  # a non-negative monotonic duration
        assert f.alive_count() == 0  # pid + last_fork dropped together

    def test_slot_out_of_range_raises(self):
        f = _Fleet(2)
        with pytest.raises(IndexError):
            f.record_fork(5, 111)

    def test_record_fork_does_not_reseed_heartbeat(self):
        # The crash-loop fix: a re-fork must NOT refresh the slot, or a child that
        # never polls looks perpetually fresh.
        f = _Fleet(1)
        f._heartbeats[0] = time.time() - 500  # an aged slot
        f.record_fork(0, 111)
        assert f.oldest_age() > 400  # still aged, not reset to ~0

    def test_immediate_crash_increments_then_loops(self):
        f = _Fleet(1)
        for i in range(1, _CRASH_LOOP_THRESHOLD + 1):
            n = f.schedule_restart(0, uptime=0.1)  # died immediately
            assert n == i
        assert f.is_crash_looping() is True

    def test_healthy_uptime_resets_crash_counter(self):
        f = _Fleet(1)
        f.schedule_restart(0, uptime=0.1)
        assert f.schedule_restart(0, uptime=0.1) == 2
        n = f.schedule_restart(0, uptime=_MIN_HEALTHY_UPTIME_SECONDS + 1)
        assert n == 0 and f.is_crash_looping() is False

    def test_freshness_is_inf_when_crash_looping(self):
        import math

        f = _Fleet(1)
        for _ in range(_CRASH_LOOP_THRESHOLD):
            f.schedule_restart(0, uptime=0.1)
        assert math.isinf(f.freshness())

    def test_freshness_is_oldest_age_when_healthy(self):
        f = _Fleet(2)
        f._heartbeats[1] = time.time() - 100
        assert 99 < f.freshness() < 102

    def test_due_restarts_respects_backoff(self, monkeypatch):
        f = _Fleet(1)
        clock = [1000.0]
        monkeypatch.setattr(f"{_MOD}.time.monotonic", lambda: clock[0])
        f.schedule_restart(0, uptime=0.1)  # backoff scheduled in the future
        assert f.due_restarts() == []  # not yet due
        clock[0] += 100.0  # well past any backoff
        assert f.due_restarts() == [0]


class TestReapDead:
    def test_dead_child_reaped_and_rescheduled(self):
        f = _Fleet(1)
        f.record_fork(0, 111)
        stopping = threading.Event()
        with patch(f"{_MOD}.os.waitpid", return_value=(111, 0)):  # exited
            _reap_dead(f, stopping)
        assert f.alive_count() == 0
        assert f.due_restarts() in ([], [0])  # scheduled (maybe backed off)
        assert f._consecutive_crashes.get(0, 0) >= 1  # counted (immediate death)

    def test_live_child_left_alone(self):
        f = _Fleet(1)
        f.record_fork(0, 111)
        with patch(f"{_MOD}.os.waitpid", return_value=(0, 0)):  # alive
            _reap_dead(f, threading.Event())
        assert f.alive_items() == [(0, 111)]

    def test_not_rescheduled_while_stopping(self):
        f = _Fleet(1)
        f.record_fork(0, 111)
        stopping = threading.Event()
        stopping.set()
        with patch(f"{_MOD}.os.waitpid", return_value=(111, 0)):
            _reap_dead(f, stopping)
        assert f.alive_count() == 0  # reaped
        assert f.due_restarts() == []  # but NOT scheduled for restart

    def test_already_reaped_is_treated_gone(self):
        f = _Fleet(1)
        f.record_fork(0, 111)
        with patch(f"{_MOD}.os.waitpid", side_effect=ChildProcessError()):
            _reap_dead(f, threading.Event())
        assert f.alive_count() == 0


class TestRestartDueChildren:
    def test_due_slot_is_reforked(self):
        f = _Fleet(1)
        f.schedule_restart(0, uptime=0.1)
        with (
            patch(f"{_MOD}.time.monotonic", return_value=1e9),  # everything due
            patch(f"{_MOD}._try_fork_child") as fork,
        ):
            _restart_due_children(f, threading.Event())
        fork.assert_called_once_with(f, 0)

    def test_stopping_blocks_refork(self):
        f = _Fleet(1)
        f.schedule_restart(0, uptime=0.1)
        stopping = threading.Event()
        stopping.set()
        with (
            patch(f"{_MOD}.time.monotonic", return_value=1e9),
            patch(f"{_MOD}._try_fork_child") as fork,
        ):
            _restart_due_children(f, stopping)
        fork.assert_not_called()  # no fresh child spawned into shutdown


class TestTryForkChild:
    def test_fork_oserror_returns_false_and_does_not_record(self):
        f = _Fleet(1)
        with patch(f"{_MOD}.os.fork", side_effect=OSError(errno.EAGAIN, "again")):
            assert _try_fork_child(f, 0) is False
        assert f.alive_count() == 0  # slot left for the next monitor tick

    def test_parent_records_child(self):
        f = _Fleet(1)
        with patch(f"{_MOD}.os.fork", return_value=222):  # parent sees child pid
            assert _try_fork_child(f, 0) is True
        assert f.alive_items() == [(0, 222)]


class TestChildAfterFork:
    def test_resets_signals_and_exits_zero_on_clean_run(self):
        with (
            patch(f"{_MOD}.signal.signal") as sig,
            patch(f"{_MOD}._run_child"),
            patch(f"{_MOD}.os._exit", side_effect=SystemExit) as exit_,
        ):
            with pytest.raises(SystemExit):
                _child_after_fork(0, MagicMock())
        # SIGTERM + SIGINT reset to default before running.
        assert sig.call_count == 2
        exit_.assert_called_once_with(0)

    def test_hard_exits_one_when_run_raises(self):
        with (
            patch(f"{_MOD}.signal.signal"),
            patch(f"{_MOD}._run_child", side_effect=RuntimeError("boom")),
            patch(f"{_MOD}.os._exit", side_effect=SystemExit) as exit_,
        ):
            with pytest.raises(SystemExit):
                _child_after_fork(0, MagicMock())
        exit_.assert_called_once_with(1)


class TestWaitForExit:
    def test_true_when_child_exits(self):
        with patch(f"{_MOD}.os.waitpid", return_value=(111, 0)):
            assert _wait_for_exit(111, time.monotonic() + 5) is True

    def test_true_when_already_reaped(self):
        with patch(f"{_MOD}.os.waitpid", side_effect=ChildProcessError()):
            assert _wait_for_exit(111, time.monotonic() + 5) is True

    def test_false_when_deadline_passes(self):
        with patch(f"{_MOD}.os.waitpid", return_value=(0, 0)):  # never exits
            assert _wait_for_exit(111, time.monotonic() - 1) is False  # already past


class TestJoinChildren:
    def test_clean_exit_no_sigkill(self):
        f = _Fleet(1)
        f.record_fork(0, 111)
        with (
            patch(f"{_MOD}._wait_for_exit", return_value=True),
            patch(f"{_MOD}.os.kill") as kill,
        ):
            _join_children(f, grace_seconds=5)
        kill.assert_not_called()

    def test_straggler_is_sigkilled_and_reaped(self):
        f = _Fleet(1)
        f.record_fork(0, 111)
        with (
            patch(f"{_MOD}._wait_for_exit", return_value=False),  # never drained
            patch(f"{_MOD}.os.kill") as kill,
            patch(f"{_MOD}.os.waitpid") as waitpid,
        ):
            _join_children(f, grace_seconds=5)
        import signal as _signal

        kill.assert_called_once_with(111, _signal.SIGKILL)
        waitpid.assert_called_once_with(111, 0)

    def test_shared_deadline_not_per_child(self):
        # UN-3695 / debate H2: all children waited against ONE shared deadline (a
        # per-child deadline serializes N wedged children to N×grace and blows past
        # the pod terminationGracePeriodSeconds → siblings hard-killed). Advancing
        # time.monotonic pins it: shared → the deadline is computed once (105 for
        # all three); a per-child recompute would yield 105/205/305.
        f = _Fleet(3)
        for slot, pid in enumerate((111, 222, 333)):
            f.record_fork(slot, pid)
        deadlines: list[float] = []

        def _record_drained(_pid, deadline):
            deadlines.append(deadline)
            return True  # child exited within the window

        with (
            patch(f"{_MOD}.time.monotonic", side_effect=[100.0, 200.0, 300.0, 400.0]),
            patch(f"{_MOD}._wait_for_exit", side_effect=_record_drained),
        ):
            _join_children(f, grace_seconds=5)
        assert deadlines == pytest.approx([105.0, 105.0, 105.0])  # computed once, shared

    def test_multi_child_stragglers_share_deadline_and_all_sigkilled(self):
        # 3 wedged children (none drain) → each SIGKILLed + reaped against the SAME
        # shared deadline. Kill-count alone wouldn't catch a per-child regression,
        # so also assert the deadline handed to every child was identical.
        f = _Fleet(3)
        for slot, pid in enumerate((111, 222, 333)):
            f.record_fork(slot, pid)
        seen: list[float] = []

        def _record_wedged(_pid, deadline):
            seen.append(deadline)
            return False  # never drains → forces SIGKILL

        with (
            patch(f"{_MOD}._wait_for_exit", side_effect=_record_wedged),
            patch(f"{_MOD}.os.kill") as kill,
            patch(f"{_MOD}.os.waitpid") as waitpid,
        ):
            _join_children(f, grace_seconds=5)
        assert kill.call_count == 3
        assert waitpid.call_count == 3
        assert len(set(seen)) == 1  # one shared deadline across all three


class TestSupervisorHealth:
    def test_no_port_returns_none(self, monkeypatch):
        monkeypatch.delenv("WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT", raising=False)
        assert sup._maybe_start_supervisor_health(_Fleet(1)) is None

    def test_bind_error_is_swallowed(self, monkeypatch):
        monkeypatch.setenv("WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT", "8090")
        server = MagicMock()
        server.start.side_effect = OSError(errno.EADDRINUSE, "in use")
        # LivenessServer is imported locally inside the function → patch its source.
        with patch(
            "queue_backend.pg_queue.liveness.LivenessServer", return_value=server
        ):
            # Must not propagate — the consumer keeps draining without a probe.
            assert sup._maybe_start_supervisor_health(_Fleet(1)) is None
