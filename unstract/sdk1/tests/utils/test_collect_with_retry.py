"""``collect_with_retry``: drain an iterable, retrying only before content.

Used by the streamed completion path. ``iter_with_retry`` stops retrying at
the first yielded item, but a provider stream emits bookkeeping chunks (e.g.
Anthropic ``message_start``) before any content. A failure at that point is
still a failed *request*, so it should be retried; a failure after content
started is a failed *generation* and must not be replayed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from unstract.sdk1.utils import retry_utils
from unstract.sdk1.utils.retry_utils import collect_with_retry

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def _is_content(item: str) -> bool:
    return item.startswith("c")


def _stream_factory(
    script: list[list[str | Exception]],
) -> tuple[Callable[[], Iterator[str]], list[int]]:
    """Each call replays the next script entry; an Exception entry is raised."""
    calls: list[int] = []

    def fn() -> Iterator[str]:
        idx = len(calls)
        calls.append(1)
        for item in script[idx]:
            if isinstance(item, Exception):
                raise item
            yield item

    return fn, calls


def test_returns_all_items_when_stream_succeeds() -> None:
    fn, calls = _stream_factory([["meta", "c1", "c2"]])
    result = collect_with_retry(
        fn, max_retries=2, retry_predicate=lambda _: True, is_content=_is_content
    )
    assert result == ["meta", "c1", "c2"]
    assert len(calls) == 1


def test_retries_when_failure_precedes_content() -> None:
    fn, calls = _stream_factory([["meta", TimeoutError()], ["meta", "c1"]])
    with patch.object(retry_utils.time, "sleep"):
        result = collect_with_retry(
            fn, max_retries=2, retry_predicate=lambda _: True, is_content=_is_content
        )
    # Bookkeeping items from the failed attempt are discarded, not duplicated.
    assert result == ["meta", "c1"]
    assert len(calls) == 2


def test_does_not_retry_once_content_was_received() -> None:
    fn, calls = _stream_factory([["meta", "c1", TimeoutError()], ["meta", "c1"]])
    with pytest.raises(TimeoutError):
        collect_with_retry(
            fn, max_retries=2, retry_predicate=lambda _: True, is_content=_is_content
        )
    assert len(calls) == 1


def test_does_not_retry_non_retryable_error() -> None:
    fn, calls = _stream_factory([[ValueError("bad key")], ["c1"]])
    with pytest.raises(ValueError):
        collect_with_retry(
            fn, max_retries=2, retry_predicate=lambda _: False, is_content=_is_content
        )
    assert len(calls) == 1


def test_gives_up_after_max_retries() -> None:
    fn, calls = _stream_factory([[TimeoutError()], [TimeoutError()], [TimeoutError()]])
    with patch.object(retry_utils.time, "sleep"), pytest.raises(TimeoutError):
        collect_with_retry(
            fn, max_retries=2, retry_predicate=lambda _: True, is_content=_is_content
        )
    assert len(calls) == 3


def test_closes_failed_generator_before_retrying() -> None:
    closed: list[bool] = []

    class _Gen:
        def __init__(self, fail: bool) -> None:
            self._fail = fail

        def __iter__(self) -> Iterator[str]:
            if self._fail:
                raise TimeoutError()
            yield "c1"

        def close(self) -> None:
            closed.append(True)

    attempts = iter([_Gen(fail=True), _Gen(fail=False)])
    with patch.object(retry_utils.time, "sleep"):
        result = collect_with_retry(
            lambda: next(attempts),
            max_retries=1,
            retry_predicate=lambda _: True,
            is_content=_is_content,
        )
    assert result == ["c1"]
    assert closed == [True]
