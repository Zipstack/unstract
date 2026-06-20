"""Tests for the PG-queue consumer prefork supervisor (UN-3606).

DB-free / fork-free: the env knob, the fleet-liveness staleness calc, and the
reap/restart loop are exercised in isolation (``os.waitpid`` mocked) so the suite
stays fast and deterministic — no real children, no worker bootstrap.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from pg_queue_consumer.supervisor import (
    _MAX_CONCURRENCY,
    _oldest_child_age,
    _reap_and_restart,
    concurrency_from_env,
)

_MOD = "pg_queue_consumer.supervisor"
_ENV = "WORKER_PG_QUEUE_CONSUMER_CONCURRENCY"


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

    def test_zero_raises(self, monkeypatch):
        monkeypatch.setenv(_ENV, "0")
        with pytest.raises(ValueError, match=">= 1"):
            concurrency_from_env()

    def test_negative_raises(self, monkeypatch):
        monkeypatch.setenv(_ENV, "-3")
        with pytest.raises(ValueError, match=">= 1"):
            concurrency_from_env()

    def test_non_int_raises(self, monkeypatch):
        monkeypatch.setenv(_ENV, "abc")
        with pytest.raises(ValueError, match="Invalid"):
            concurrency_from_env()


class TestOldestChildAge:
    def test_fresh_fleet_is_near_zero(self):
        now = time.time()
        assert _oldest_child_age([now, now, now]) < 1.0

    def test_returns_oldest(self):
        now = time.time()
        # One child polled 100s ago — that's the fleet's staleness.
        age = _oldest_child_age([now, now - 100, now - 5])
        assert 99 < age < 102

    def test_empty_fleet_is_zero(self):
        assert _oldest_child_age([]) == 0.0


class TestReapAndRestart:
    """The supervisor's recovery loop: dead children re-fork; the rest are left."""

    @staticmethod
    def _old(slot: int) -> dict:
        # last_fork well in the past so the rate-limit sleep is skipped.
        return {slot: time.monotonic() - 1000.0}

    def test_dead_child_is_restarted(self):
        children = {0: 111}
        fork_child = MagicMock()
        stopping = threading.Event()
        with patch(f"{_MOD}.os.waitpid", return_value=(111, 0)):  # exited
            _reap_and_restart(children, self._old(0), stopping, fork_child)
        fork_child.assert_called_once_with(0)
        assert 0 not in children  # removed before re-fork

    def test_live_child_is_left_alone(self):
        children = {0: 111}
        fork_child = MagicMock()
        stopping = threading.Event()
        with patch(f"{_MOD}.os.waitpid", return_value=(0, 0)):  # still alive
            _reap_and_restart(children, self._old(0), stopping, fork_child)
        fork_child.assert_not_called()
        assert children == {0: 111}  # untouched

    def test_dead_child_not_restarted_while_stopping(self):
        children = {0: 111}
        fork_child = MagicMock()
        stopping = threading.Event()
        stopping.set()  # graceful shutdown in progress
        with patch(f"{_MOD}.os.waitpid", return_value=(111, 0)):
            _reap_and_restart(children, self._old(0), stopping, fork_child)
        fork_child.assert_not_called()  # do NOT resurrect during shutdown
        assert 0 not in children  # but still reaped

    def test_already_reaped_child_is_restarted(self):
        """waitpid raising ChildProcessError (already reaped) is treated as gone."""
        children = {0: 111}
        fork_child = MagicMock()
        stopping = threading.Event()
        with patch(f"{_MOD}.os.waitpid", side_effect=ChildProcessError()):
            _reap_and_restart(children, self._old(0), stopping, fork_child)
        fork_child.assert_called_once_with(0)
