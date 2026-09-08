"""The retry loop must yield to an abort (UN-1031).

Without this, stopping a run can still cost a full backoff. Adapters default
to five retries with exponential delay, so a caller who pressed Stop could sit
through a minute of sleeping — and then watch the loop start another attempt —
before anything noticed.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest
from unstract.sdk1.utils.aborting import AbortedError
from unstract.sdk1.utils.retry_utils import (
    acall_with_retry,
    call_with_retry,
    is_retryable_litellm_error,
    iter_with_retry,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def _always_retryable(_: Exception) -> bool:
    return True


class _TransientError(Exception):
    pass


class TestCallWithRetry:
    def test_aborts_inside_the_backoff_not_after_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The delay itself must be interruptible."""
        monkeypatch.setattr(
            "unstract.sdk1.utils.retry_utils._get_retry_delay",
            lambda *a, **k: 10.0,
        )
        attempts = []

        def failing() -> None:
            attempts.append(1)
            raise _TransientError("transient")

        started = time.monotonic()
        with pytest.raises(AbortedError):
            call_with_retry(
                failing,
                max_retries=5,
                retry_predicate=_always_retryable,
                should_abort=lambda: len(attempts) >= 1,
            )
        elapsed = time.monotonic() - started

        assert elapsed < 2, f"sat in the backoff for {elapsed:.1f}s"
        # Crucially, the loop did not go on to burn the remaining attempts.
        assert len(attempts) == 1

    def test_aborts_before_the_first_attempt(self) -> None:
        called = []

        def fn() -> str:
            called.append(1)
            return "result"

        with pytest.raises(AbortedError):
            call_with_retry(
                fn,
                max_retries=3,
                retry_predicate=_always_retryable,
                should_abort=lambda: True,
            )
        assert called == []

    def test_without_a_predicate_behaviour_is_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "unstract.sdk1.utils.retry_utils._get_retry_delay",
            lambda *a, **k: 0.0,
        )
        attempts = []

        def flaky() -> str:
            attempts.append(1)
            if len(attempts) < 3:
                raise _TransientError("transient")
            return "ok"

        assert (
            call_with_retry(flaky, max_retries=5, retry_predicate=_always_retryable)
            == "ok"
        )
        assert len(attempts) == 3

    def test_a_broken_predicate_does_not_stop_the_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "unstract.sdk1.utils.retry_utils._get_retry_delay",
            lambda *a, **k: 0.0,
        )
        attempts = []

        def flaky() -> str:
            attempts.append(1)
            if len(attempts) < 2:
                raise _TransientError("transient")
            return "ok"

        def broken() -> None:
            raise RuntimeError("signal store down")

        assert (
            call_with_retry(
                flaky,
                max_retries=5,
                retry_predicate=_always_retryable,
                should_abort=broken,
            )
            == "ok"
        )

    def test_an_abort_is_never_treated_as_retryable(self) -> None:
        """An abort must not look transient to the production predicate.

        Otherwise the loop would retry the very call we just walked away from.
        """
        assert is_retryable_litellm_error(AbortedError("stopped")) is False

        attempts = []

        def aborting() -> None:
            attempts.append(1)
            raise AbortedError("stopped")

        # With the real predicate the error propagates on the first attempt.
        with pytest.raises(AbortedError):
            call_with_retry(
                aborting,
                max_retries=5,
                retry_predicate=is_retryable_litellm_error,
            )
        assert len(attempts) == 1


class TestAsyncCallWithRetry:
    def test_aborts_inside_the_async_backoff(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "unstract.sdk1.utils.retry_utils._get_retry_delay",
            lambda *a, **k: 10.0,
        )
        attempts = []

        async def failing() -> None:
            attempts.append(1)
            raise _TransientError("transient")

        async def run() -> object:
            return await acall_with_retry(
                failing,
                max_retries=5,
                retry_predicate=_always_retryable,
                should_abort=lambda: len(attempts) >= 1,
            )

        started = time.monotonic()
        with pytest.raises(AbortedError):
            asyncio.run(run())
        assert time.monotonic() - started < 2
        assert len(attempts) == 1


class TestIterWithRetry:
    def test_a_stream_stops_at_the_next_chunk(self) -> None:
        yielded = []
        stop_after = 3

        def stream() -> Iterator[int]:
            yield from range(100)

        gen = iter_with_retry(
            stream,
            max_retries=2,
            retry_predicate=_always_retryable,
            should_abort=lambda: len(yielded) >= stop_after,
        )
        with pytest.raises(AbortedError):
            for item in gen:
                yielded.append(item)

        # Stopped promptly rather than draining all 100.
        assert len(yielded) == stop_after

    def test_an_unaborted_stream_completes(self) -> None:
        def stream() -> Iterator[int]:
            yield from range(5)

        got = list(
            iter_with_retry(
                stream,
                max_retries=2,
                retry_predicate=_always_retryable,
                should_abort=lambda: False,
            )
        )
        assert got == [0, 1, 2, 3, 4]
