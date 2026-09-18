"""Abandoning an in-flight call (UN-1031).

The point of this machinery is that a caller who stops caring about a result
stops *waiting* for it, promptly, without the SDK learning why. What matters,
and is pinned here:

* an abort is fast even when the underlying call is not;
* the abandoned coroutine really is cancelled, not merely ignored;
* a caller who never aborts sees no behaviour change at all;
* nothing about aborting can kill healthy work — a broken predicate is
  treated as "carry on".
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from unstract.sdk1.utils.aborting import (
    AbortedError,
    abort_scope,
    current_abort_check,
    run_abortable,
    should_abort_now,
    sliced_sleep,
)


class TestRunAbortable:
    def test_returns_the_result_when_nothing_aborts(self) -> None:
        async def work() -> str:
            await asyncio.sleep(0.01)
            return "done"

        assert run_abortable(work, lambda: False) == "done"

    def test_no_predicate_at_all_is_just_run_and_wait(self) -> None:
        async def work() -> int:
            return 42

        assert run_abortable(work, None) == 42

    def test_a_long_call_is_abandoned_quickly(self) -> None:
        started = threading.Event()

        async def slow() -> str:
            started.set()
            await asyncio.sleep(30)
            return "never"

        started_at = time.monotonic()
        with pytest.raises(AbortedError):
            # Aborts as soon as the first poll sees the predicate.
            run_abortable(slow, lambda: started.is_set(), poll=0.05)
        elapsed = time.monotonic() - started_at

        # The call would have taken 30s; we must not have waited for it.
        assert elapsed < 5, f"abort took {elapsed:.1f}s"

    def test_the_abandoned_coroutine_is_actually_cancelled(self) -> None:
        """Not merely ignored — the request underneath really is dropped."""
        observed = threading.Event()

        async def slow() -> None:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                observed.set()
                raise

        with pytest.raises(AbortedError):
            run_abortable(slow, lambda: True, poll=0.05)

        assert observed.wait(timeout=5), "coroutine never saw CancelledError"

    def test_an_error_inside_the_call_still_surfaces(self) -> None:
        async def boom() -> None:
            raise ValueError("provider said no")

        with pytest.raises(ValueError, match="provider said no"):
            run_abortable(boom, lambda: False)

    def test_a_broken_predicate_does_not_abort_the_work(self) -> None:
        def broken() -> None:
            raise RuntimeError("redis is down")

        async def work() -> str:
            await asyncio.sleep(0.01)
            return "completed anyway"

        # A cache outage must never kill a healthy run.
        assert run_abortable(work, broken, poll=0.02) == "completed anyway"

    def test_concurrent_callers_from_different_threads(self) -> None:
        """One shared loop serves every caller, so this must hold."""
        results: dict[str, object] = {}

        async def quick() -> str:
            await asyncio.sleep(0.05)
            return "ok"

        async def slow() -> str:
            await asyncio.sleep(30)
            return "never"

        def run_quick() -> None:
            results["quick"] = run_abortable(quick, lambda: False)

        def run_slow() -> None:
            try:
                run_abortable(slow, lambda: True, poll=0.05)
            except AbortedError:
                results["slow"] = "aborted"

        threads = [threading.Thread(target=run_quick), threading.Thread(target=run_slow)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        assert results == {"quick": "ok", "slow": "aborted"}

    def test_the_loop_survives_across_calls(self) -> None:
        """A closed loop would poison litellm's cached async clients."""

        async def work() -> str:
            return "ok"

        assert run_abortable(work, lambda: False) == "ok"
        assert run_abortable(work, lambda: False) == "ok"
        assert run_abortable(work, lambda: False) == "ok"

    def test_refuses_to_nest_inside_a_running_loop(self) -> None:
        """Blocking on another loop from inside one would deadlock it."""

        async def outer() -> None:
            async def inner() -> str:
                return "nope"

            with pytest.raises(RuntimeError, match="running event loop"):
                run_abortable(inner, lambda: False)

        asyncio.run(outer())


class TestAmbientScope:
    def test_no_scope_means_no_abort(self) -> None:
        assert current_abort_check() is None
        assert should_abort_now() is False

    def test_scope_supplies_the_predicate_to_code_that_never_saw_it(self) -> None:
        with abort_scope(lambda: True):
            assert should_abort_now() is True
        assert should_abort_now() is False

    def test_scopes_nest_and_restore(self) -> None:
        with abort_scope(lambda: False):
            with abort_scope(lambda: True):
                assert should_abort_now() is True
            assert should_abort_now() is False

    def test_an_explicit_none_scopes_a_region_as_non_abortable(self) -> None:
        with abort_scope(lambda: True):
            with abort_scope(None):
                assert should_abort_now() is False

    def test_run_abortable_picks_up_the_ambient_predicate(self) -> None:
        async def slow() -> None:
            await asyncio.sleep(30)

        with abort_scope(lambda: True):
            with pytest.raises(AbortedError):
                run_abortable(slow, poll=0.05)


class TestSlicedSleep:
    def test_sleeps_the_full_time_when_nothing_aborts(self) -> None:
        started = time.monotonic()
        sliced_sleep(0.3, lambda: False, slice_seconds=0.05)
        assert time.monotonic() - started >= 0.25

    def test_wakes_early_on_abort(self) -> None:
        """A backoff can reach a minute; a stop must not sit inside one."""
        started = time.monotonic()
        with pytest.raises(AbortedError):
            sliced_sleep(30, lambda: True, slice_seconds=0.05)
        assert time.monotonic() - started < 2

    def test_zero_and_negative_are_no_ops(self) -> None:
        sliced_sleep(0, lambda: True)
        sliced_sleep(-1, lambda: True)

    def test_without_a_predicate_it_is_an_ordinary_sleep(self) -> None:
        started = time.monotonic()
        sliced_sleep(0.1, None)
        assert time.monotonic() - started >= 0.08
