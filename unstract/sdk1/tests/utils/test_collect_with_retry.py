"""``collect_with_retry``: drain an iterable, retrying only before content.

Used by the streamed completion path. ``iter_with_retry`` stops retrying at
the first yielded item, but a provider stream emits bookkeeping chunks (e.g.
Anthropic ``message_start``) before any content. A failure at that point is
still a failed *request*, so it should be retried; a failure after content
started is a failed *generation* and must not be replayed.
"""

from __future__ import annotations

import logging
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


def test_retries_when_stream_creation_itself_raises() -> None:
    """``fn()`` failing before returning an iterable is a failed request.

    litellm's streaming ``completion()`` sends the HTTP request when called,
    so a 429/5xx/connection error surfaces from ``fn()`` itself rather than
    from iteration.
    """
    calls: list[int] = []

    def fn() -> Iterator[str]:
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("request failed before any chunk")
        return iter(["meta", "c1"])

    with patch.object(retry_utils.time, "sleep"):
        result = collect_with_retry(
            fn, max_retries=2, retry_predicate=lambda _: True, is_content=_is_content
        )
    assert result == ["meta", "c1"]
    assert len(calls) == 2


def test_stream_creation_failure_that_is_not_retryable_is_raised() -> None:
    calls: list[int] = []

    def fn() -> Iterator[str]:
        calls.append(1)
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        collect_with_retry(
            fn, max_retries=2, retry_predicate=lambda _: False, is_content=_is_content
        )
    assert len(calls) == 1


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

    def _sleep(_: float) -> None:
        # The failed attempt is released before the backoff, not after.
        assert closed == [True]

    with patch.object(retry_utils.time, "sleep", side_effect=_sleep):
        result = collect_with_retry(
            lambda: next(attempts),
            max_retries=1,
            retry_predicate=lambda _: True,
            is_content=_is_content,
        )
    assert result == ["c1"]
    # Both attempts: the failed one and the successful one (UN-4237).
    assert closed == [True, True]


# ── Releasing the HTTP response (UN-4237) ────────────────────────────────────
#
# A stream left open is closed by the garbage collector, possibly while the
# thread holds httpcore's non-reentrant pool lock, which deadlocks the worker.
# LiteLLM's sync stream wrapper has no ``close()`` and stops before the HTTP
# body ends, so every stream must be closed explicitly, through the handles
# the wrapper holds. ``test_stream_connection_release.py`` covers this against
# a real socket.


class _Closable:
    def __init__(self, name: str, log: list[str]) -> None:
        self._name = name
        self._log = log

    def close(self) -> None:
        self._log.append(self._name)


class _ProviderIterator:
    """Shaped like litellm's ``ModelResponseIterator``."""

    def __init__(self, log: list[str]) -> None:
        self.streaming_response = _Closable("lines", log)
        self.response = _Closable("response", log)


class _Wrapper:
    """Shaped like litellm's sync ``CustomStreamWrapper``: no ``close()``."""

    def __init__(self, items: list[str | Exception], log: list[str]) -> None:
        self._items = items
        self.completion_stream = _ProviderIterator(log)

    def __iter__(self) -> Iterator[str]:
        for item in self._items:
            if isinstance(item, Exception):
                raise item
            yield item


def test_close_stream_reaches_the_response_behind_a_wrapper() -> None:
    log: list[str] = []
    retry_utils.close_stream(_Wrapper([], log))
    assert sorted(log) == ["lines", "response"]


def test_close_stream_ignores_none_and_objects_without_close() -> None:
    retry_utils.close_stream(None)
    retry_utils.close_stream(iter(["c1"]))
    retry_utils.close_stream(object())


def test_close_stream_never_raises() -> None:
    class _Broken:
        def close(self) -> None:
            raise RuntimeError("already torn down")

    retry_utils.close_stream(_Broken())


def test_failed_close_is_logged_as_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    """A close that raises can leave the pool slot checked out for good."""

    class _Broken:
        def close(self) -> None:
            raise RuntimeError("already torn down")

    with caplog.at_level(logging.WARNING, logger=retry_utils.logger.name):
        retry_utils.close_stream(_Broken())

    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert "_Broken" in record.getMessage()
    assert record.exc_info is not None


def _bedrock_shaped(log: list[str], fail_after_first: bool = False) -> object:
    """A wrapper whose ``completion_stream`` is a plain generator, as on Bedrock.

    There is no response handle to reach: closing the generator itself is the
    only thing that releases the connection. With ``fail_after_first`` the
    wrapper raises while the provider generator is still suspended, as
    litellm does on a mid-stream error.
    """

    def provider_stream() -> Iterator[str]:
        try:
            yield "c1"
            yield "c2"
        finally:
            log.append("generator")

    class _Wrapper:
        def __init__(self) -> None:
            self.completion_stream = provider_stream()

        def __iter__(self) -> Iterator[str]:
            for item in self.completion_stream:
                yield item
                if fail_after_first:
                    raise TimeoutError("mid-stream")

    return _Wrapper()


def test_close_stream_closes_a_generator_completion_stream() -> None:
    log: list[str] = []
    wrapper = _bedrock_shaped(log)
    next(iter(wrapper))

    retry_utils.close_stream(wrapper)

    assert log == ["generator"]


def test_collect_with_retry_closes_a_generator_completion_stream_on_error() -> None:
    log: list[str] = []
    # Held here so reference counting cannot finalise the generator once the
    # call returns: only an explicit close may run its ``finally``.
    opened: list[object] = []

    def open_stream() -> object:
        opened.append(_bedrock_shaped(log, fail_after_first=True))
        return opened[-1]

    with pytest.raises(TimeoutError):
        collect_with_retry(
            open_stream,
            max_retries=0,
            retry_predicate=lambda _: True,
            is_content=_is_content,
        )

    assert log == ["generator"]


def test_close_stream_closes_an_openai_sdk_shaped_stream() -> None:
    """The OpenAI SDK ``Stream``: its own ``close()`` plus ``.response``."""
    log: list[str] = []

    class _Stream:
        def __init__(self) -> None:
            self.response = _Closable("response", log)

        def close(self) -> None:
            log.append("stream")

    class _Wrapper:
        completion_stream = _Stream()

    retry_utils.close_stream(_Wrapper())

    assert sorted(log) == ["response", "stream"]


def test_close_stream_reaches_the_responses_api_response() -> None:
    """The Responses-API bridge keeps the response two iterators down.

    Shaped like litellm 1.104.0: the wrapper's ``completion_stream`` is the
    bridge, whose ``streaming_response`` is an iterator with no ``close()``
    holding ``response`` and ``stream_iterator``.
    """
    log: list[str] = []

    class _ResponsesIterator:  # no close()
        def __init__(self) -> None:
            self.response = _Closable("response", log)
            self.stream_iterator = _Closable("stream_iterator", log)

    class _Bridge:  # no close()
        streaming_response = _ResponsesIterator()

    class _Wrapper:
        completion_stream = _Bridge()

    retry_utils.close_stream(_Wrapper())

    assert sorted(log) == ["response", "stream_iterator"]


def test_close_stream_closes_each_object_once_and_terminates_on_cycles() -> None:
    log: list[str] = []

    class _Loop:
        def __init__(self) -> None:
            self.response = self
            self.completion_stream = self

        def close(self) -> None:
            log.append("loop")

    retry_utils.close_stream(_Loop())

    assert log == ["loop"]


def test_closes_drained_stream_on_success() -> None:
    log: list[str] = []
    result = collect_with_retry(
        lambda: _Wrapper(["meta", "c1"], log),
        max_retries=0,
        retry_predicate=lambda _: True,
        is_content=_is_content,
    )
    assert result == ["meta", "c1"]
    assert sorted(log) == ["lines", "response"]


def test_closes_stream_when_failure_after_content_is_raised() -> None:
    log: list[str] = []
    with pytest.raises(TimeoutError):
        collect_with_retry(
            lambda: _Wrapper(["c1", TimeoutError()], log),
            max_retries=2,
            retry_predicate=lambda _: True,
            is_content=_is_content,
        )
    assert sorted(log) == ["lines", "response"]


def test_close_failure_does_not_mask_the_stream_error() -> None:
    class _Gen:
        def __iter__(self) -> Iterator[str]:
            raise ValueError("bad request")

        def close(self) -> None:
            raise RuntimeError("close failed")

    with pytest.raises(ValueError, match="bad request"):
        collect_with_retry(
            _Gen, max_retries=0, retry_predicate=lambda _: False, is_content=_is_content
        )


def test_iter_with_retry_closes_stream_on_success() -> None:
    log: list[str] = []
    result = list(
        retry_utils.iter_with_retry(
            lambda: _Wrapper(["meta", "c1"], log),
            max_retries=0,
            retry_predicate=lambda _: True,
        )
    )
    assert result == ["meta", "c1"]
    assert sorted(log) == ["lines", "response"]


def test_iter_with_retry_closes_stream_when_caller_stops_early() -> None:
    log: list[str] = []
    gen = retry_utils.iter_with_retry(
        lambda: _Wrapper(["c1", "c2"], log),
        max_retries=0,
        retry_predicate=lambda _: True,
    )
    assert next(gen) == "c1"
    gen.close()
    assert sorted(log) == ["lines", "response"]


def test_iter_with_retry_closes_failed_attempt_before_backoff() -> None:
    log: list[str] = []
    attempts = iter([_Wrapper([TimeoutError()], log), _Wrapper(["c1"], log)])

    def _sleep(_: float) -> None:
        assert sorted(log) == ["lines", "response"]

    with patch.object(retry_utils.time, "sleep", side_effect=_sleep):
        result = list(
            retry_utils.iter_with_retry(
                lambda: next(attempts),
                max_retries=1,
                retry_predicate=lambda _: True,
            )
        )
    assert result == ["c1"]
    assert len(log) == 4
