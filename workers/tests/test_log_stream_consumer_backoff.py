"""Tests for the log-stream consumer's backoff while Redis is unreachable.

A refused or unresolvable connect makes BLMOVE raise at once, so BLMOVE's own block
never happens. Retrying immediately spun the loop at ~1k iterations/s, each writing a
traceback. These pin the wait schedule, the length of each wait, its reset on the next
reply, prompt shutdown during a wait, and that errors from a server that did answer
keep today's behaviour.

Loaded over the same faked worker-framework imports as ``test_log_stream_consumer.py``;
the redis exception classes are the real ones, since they decide which branch runs.
"""

from __future__ import annotations

import os
import signal
import threading
import time
import types
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import (
    AuthenticationError,
    BusyLoadingError,
    ReadOnlyError,
    ResponseError,
)
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.sentinel import MasterNotFoundError

from .test_log_stream_consumer import _envelope, _load

_REFUSED = RedisConnectionError("Error 111 connecting to redis:6379. Connection refused.")


@pytest.fixture
def consumer(monkeypatch):
    # run() installs SIGTERM/SIGINT handlers on this process; put pytest's back.
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    yield _load(monkeypatch)
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def _scripted_redis(consumer, outcomes):
    """A redis mock whose BLMOVE yields ``outcomes`` in turn, then ends the loop.

    An exception instance is raised rather than returned. ``lmove`` returns None so
    startup recovery finds nothing, as a real Redis does on an empty list.
    """
    redis = MagicMock()
    redis.lmove.return_value = None
    pending = list(outcomes)

    def _blmove(*_a, **_k):
        if not pending:
            consumer._shutdown = True
            return None
        outcome = pending.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    redis.blmove.side_effect = _blmove
    return redis


def _run_recording_waits(consumer, redis):
    """Run the loop with the wait replaced by a recorder; return the requested waits."""
    waits = []
    with (
        patch.object(consumer, "create_redis_client", return_value=redis),
        patch.object(consumer, "_wait_before_reconnect", side_effect=waits.append),
    ):
        assert consumer.run() == 0
    return waits


class TestBackoffSchedule:
    def test_waits_double_from_one_second_and_cap_at_thirty(self, consumer):
        redis = _scripted_redis(consumer, [_REFUSED] * 8)
        assert _run_recording_waits(consumer, redis) == [1, 2, 4, 8, 16, 30, 30, 30]

    @pytest.mark.parametrize(
        "error",
        [
            _REFUSED,
            RedisTimeoutError("Timeout connecting to server"),
            # Subclasses of ConnectionError that reach BLMOVE in production: a rotated
            # password, a replica still loading its RDB, and Sentinel with no master.
            AuthenticationError("invalid username-password pair"),
            BusyLoadingError("Redis is loading the dataset in memory"),
            MasterNotFoundError("No master found for 'mymaster'"),
        ],
        ids=lambda e: type(e).__name__,
    )
    def test_every_connection_level_error_backs_off(self, consumer, error):
        redis = _scripted_redis(consumer, [error])
        assert _run_recording_waits(consumer, redis) == [1]

    def test_an_idle_none_reply_resets_the_backoff(self, consumer):
        # BLMOVE timing out with no work is still a round trip: Redis is back.
        redis = _scripted_redis(consumer, [_REFUSED] * 3 + [None] + [_REFUSED] * 2)
        assert _run_recording_waits(consumer, redis) == [1, 2, 4, 1, 2]

    def test_the_failure_log_says_it_is_backing_off_and_for_how_long(self, consumer):
        redis = _scripted_redis(consumer, [_REFUSED, _REFUSED])
        _run_recording_waits(consumer, redis)

        calls = consumer.logger.error.call_args_list
        assert [c.args[0] % c.args[1:] for c in calls] == [
            "Log stream read failed: Redis unavailable; backing off 1s before retrying",
            "Log stream read failed: Redis unavailable; backing off 2s before retrying",
        ]
        assert all(c.kwargs.get("exc_info") is True for c in calls)


class TestRecovery:
    def test_an_envelope_after_recovery_is_dispatched_and_removed(self, consumer):
        raw = _envelope(event="logs:c1", user_session_id="c1")
        redis = _scripted_redis(consumer, [_REFUSED, _REFUSED, raw, _REFUSED])

        waits = _run_recording_waits(consumer, redis)

        consumer._test_logs_consumer.assert_called_once_with(
            event="logs:c1", user_session_id="c1"
        )
        redis.lrem.assert_called_once_with("log_stream_queue:processing:pod-abc", 1, raw)
        # The delivered envelope reset the schedule for the next outage.
        assert waits == [1, 2, 1]


class TestErrorsFromAServerThatAnswered:
    """Out of scope for the backoff: still logged and retried at once, as before."""

    def test_are_logged_and_retried_without_waiting(self, consumer):
        errors = [
            ReadOnlyError("You can't write against a read only replica."),
            ResponseError("WRONGTYPE Operation against a key holding the wrong kind"),
            ValueError("not a redis error at all"),
        ]
        redis = _scripted_redis(consumer, errors)

        assert _run_recording_waits(consumer, redis) == []
        assert redis.blmove.call_count == len(errors) + 1
        assert consumer.logger.error.call_count == len(errors)
        for call in consumer.logger.error.call_args_list:
            assert call.args == ("Log stream read failed; retrying",)
            assert call.kwargs == {"exc_info": True}


class TestShutdownDuringBackoff:
    def test_sigterm_mid_wait_ends_run_promptly(self, consumer, monkeypatch):
        # Make the first wait 30s, so "prompt" is unmistakable.
        monkeypatch.setattr(consumer, "_RECONNECT_BACKOFF_INITIAL_SECONDS", 30.0)
        handler_installed = []

        def _sigterm_self():
            # Only signal once run()'s handler is in place; otherwise SIGTERM's default
            # action would kill the test process instead of failing the test.
            if signal.getsignal(signal.SIGTERM) is consumer._handle_signal:
                handler_installed.append(True)
                os.kill(os.getpid(), signal.SIGTERM)
            else:
                consumer._shutdown = True

        redis = MagicMock()
        redis.lmove.return_value = None

        def _blmove(*_a, **_k):
            if redis.blmove.call_count == 1:
                threading.Timer(0.2, _sigterm_self).start()
            raise _REFUSED

        redis.blmove.side_effect = _blmove

        start = time.monotonic()
        with patch.object(consumer, "create_redis_client", return_value=redis):
            assert consumer.run() == 0
        elapsed = time.monotonic() - start

        assert handler_installed, "run() did not install its SIGTERM handler"
        # 0.2s until the signal, plus the rest of the slice it landed in (PEP 475 resumes
        # that sleep). A fixed bound, not one built from _SHUTDOWN_POLL_SECONDS: raising
        # that constant is the very regression this guards. Generous for slow CI, and
        # far below the 30s wait it interrupted.
        assert elapsed < 2.0
        # Shutdown was noticed without another attempt at Redis.
        assert redis.blmove.call_count == 1

    def test_without_a_signal_the_wait_lasts_its_full_duration(self, consumer):
        # Guards against a wait that silently returns at once — the spin again.
        start = time.monotonic()
        consumer._wait_before_reconnect(0.3)
        assert 0.3 <= time.monotonic() - start < 2.0

    def test_the_wait_returns_at_once_when_shutdown_is_already_requested(self, consumer):
        consumer._shutdown = True
        start = time.monotonic()
        consumer._wait_before_reconnect(30)
        assert time.monotonic() - start < 0.5


def _fake_clock(consumer, monkeypatch, on_sleep=None):
    """Swap the module's ``time`` for a clock that moves only when slept on.

    Returns the list of slices the wait slept for, so a test can check the total and
    the slice length without sleeping for real.
    """
    now = [1000.0]
    slices = []

    def _sleep(seconds):
        slices.append(seconds)
        now[0] += seconds
        if on_sleep:
            on_sleep()

    monkeypatch.setattr(
        consumer, "time", types.SimpleNamespace(monotonic=lambda: now[0], sleep=_sleep)
    )
    return slices


class TestTheWaitItself:
    """The loop tests replace the wait with a recorder; these pin what it then does."""

    @pytest.mark.parametrize("seconds", [1.0, 4.0, 30.0])
    def test_lasts_the_whole_request_in_short_slices(
        self, consumer, monkeypatch, seconds
    ):
        slices = _fake_clock(consumer, monkeypatch)
        consumer._wait_before_reconnect(seconds)
        # Exactly the request: shorter brings the log flood back, longer delays recovery.
        assert sum(slices) == pytest.approx(seconds)
        # A slice is how late SIGTERM can be noticed, so bound it absolutely.
        assert max(slices) <= 1.0

    def test_stops_after_the_slice_in_which_shutdown_arrives(self, consumer, monkeypatch):
        def _request_shutdown():
            consumer._shutdown = True

        slices = _fake_clock(consumer, monkeypatch, on_sleep=_request_shutdown)
        consumer._wait_before_reconnect(30.0)
        assert len(slices) == 1
        assert slices[0] <= 1.0
