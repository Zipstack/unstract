"""``LLM.complete()`` streams under the hood for direct Anthropic.

A non-streaming Anthropic request keeps the socket silent for the whole
generation. For long replies the response never arrives: the client's read
timeout fires (900 s / 1800 s observed in staging and production) and the
identical request was replayed by the retry helper. Anthropic's own SDK
refuses non-streaming requests expected to exceed 10 minutes for this reason.

These tests pin the contract: for the ``anthropic`` provider ``complete()``
issues ``stream=True``, collects the chunks and rebuilds the same response
shape callers already consume. Every provider streams unless its adapter
opts out.

LiteLLM's ``mock_response`` streaming path produces real ``ModelResponseStream``
chunks, so the rebuild goes through ``litellm.stream_chunk_builder`` for real.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib import import_module
from typing import TYPE_CHECKING
from unittest.mock import patch

import litellm
import pytest
from unstract.sdk1.utils import retry_utils

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

ANTHROPIC_ADAPTER_ID = "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203"
OPENAI_ADAPTER_ID = "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17"
MOCK_TEXT = "hello streamed world"
# Bound before any test patches ``litellm.completion`` so the spy can delegate
# to the real mock path instead of recursing into itself.
_REAL_COMPLETION = litellm.completion


@lru_cache(maxsize=1)
def _load_llm_module() -> object:
    import sys
    from types import ModuleType

    sys.modules.setdefault("magic", ModuleType("magic"))
    return import_module("unstract.sdk1.llm")


def _make_llm(adapter_id: str, model: str, **metadata: object) -> object:
    llm_module = _load_llm_module()
    return llm_module.LLM(
        adapter_id=adapter_id,
        adapter_metadata={"model": model, "api_key": "test-key", **metadata},
    )


def _mock_chunks(model: str) -> list[object]:
    """Real litellm stream chunks for MOCK_TEXT, produced without network."""
    return list(
        _REAL_COMPLETION(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
            mock_response=MOCK_TEXT,
            api_key="test-key",
        )
    )


class _Spy:
    """Record litellm.completion kwargs and delegate to the mock path."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return _REAL_COMPLETION(**{**kwargs, "mock_response": MOCK_TEXT})


@pytest.fixture
def no_cost() -> Iterator[None]:
    llm_module = _load_llm_module()
    with patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)):
        yield


# ── Anthropic streams under the hood ─────────────────────────────────────────


def test_anthropic_complete_streams_under_the_hood(no_cost: None) -> None:
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6")
    spy = _Spy()

    with patch.object(llm_module.litellm, "completion", spy):
        result = llm.complete("hi")

    assert len(spy.calls) == 1
    assert spy.calls[0]["stream"] is True
    assert result["response"].text == MOCK_TEXT


def test_anthropic_rebuilt_response_keeps_consumer_facing_fields(
    no_cost: None,
) -> None:
    """Rebuilt raw response keeps finish_reason and usage.

    Callers read ``raw.choices[0].finish_reason`` and usage off the raw
    response (cloud line-item extractor, usage accounting).
    """
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6")

    with patch.object(llm_module.litellm, "completion", _Spy()):
        result = llm.complete("hi")

    raw = result["response"].raw
    assert raw.choices[0].finish_reason == "stop"
    assert raw["choices"][0]["message"]["content"] == MOCK_TEXT
    assert raw.get("usage") is not None
    assert raw["usage"]["completion_tokens"] > 0


def test_anthropic_stream_records_usage_once(
    no_cost: None, caplog: pytest.LogCaptureFixture
) -> None:
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6")

    with (
        patch.object(llm_module.litellm, "completion", _Spy()),
        caplog.at_level(logging.INFO, logger=llm_module.logger.name),
    ):
        llm.complete("hi")

    usage_logs = [r.message for r in caplog.records if "Usage:" in r.message]
    assert len(usage_logs) == 1
    assert "[complete]" in usage_logs[0]


def test_adapter_opted_out_stays_non_streaming(no_cost: None) -> None:
    llm_module = _load_llm_module()
    llm = _make_llm(
        OPENAI_ADAPTER_ID,
        "gpt-4o",
        api_base="https://api.openai.com/v1",
        enable_streaming=False,
    )
    spy = _Spy()

    with patch.object(llm_module.litellm, "completion", spy):
        result = llm.complete("hi")

    assert len(spy.calls) == 1
    assert not spy.calls[0].get("stream")
    assert result["response"].text == MOCK_TEXT


# ── Retry semantics on the streamed path ─────────────────────────────────────


def _failing_then_ok(
    chunks: list[object], fail_after: int, error: Exception
) -> tuple[Callable[..., Iterator[object]], list[int]]:
    """Build a litellm.completion stand-in that fails once, then succeeds.

    The first call raises ``error`` after yielding ``fail_after`` chunks; the
    second call yields every chunk.
    """
    calls: list[int] = []

    def fake(**_: object) -> Iterator[object]:
        calls.append(1)
        if len(calls) == 1:
            yield from chunks[:fail_after]
            raise error
        yield from chunks

    return fake, calls


def _timeout() -> Exception:
    return litellm.Timeout(
        message="Connection timed out after 900.0 seconds.",
        model="claude-sonnet-4-6",
        llm_provider="anthropic",
    )


def test_stream_failure_before_any_content_is_retried(no_cost: None) -> None:
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6", max_retries=2)
    chunks = _mock_chunks("anthropic/claude-sonnet-4-6")
    fake, calls = _failing_then_ok(chunks, fail_after=0, error=_timeout())

    with (
        patch.object(llm_module.litellm, "completion", fake),
        patch.object(retry_utils.time, "sleep") as fake_sleep,
    ):
        result = llm.complete("hi")

    assert len(calls) == 2
    assert result["response"].text == MOCK_TEXT
    fake_sleep.assert_called_once()


def test_request_failure_before_stream_exists_is_retried(no_cost: None) -> None:
    """Litellm raises from ``completion()`` itself on request errors.

    A rate limit or connection error happens before a stream object exists,
    so it must be retried like a non-streaming call, not escape on the first
    attempt.
    """
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6", max_retries=2)
    chunks = _mock_chunks("anthropic/claude-sonnet-4-6")
    calls: list[int] = []

    def fake(**_: object) -> Iterator[object]:
        calls.append(1)
        if len(calls) == 1:
            raise litellm.RateLimitError(
                message="rate limited",
                model="claude-sonnet-4-6",
                llm_provider="anthropic",
            )
        return iter(chunks)

    with (
        patch.object(llm_module.litellm, "completion", fake),
        patch.object(retry_utils.time, "sleep") as fake_sleep,
    ):
        result = llm.complete("hi")

    assert len(calls) == 2
    assert result["response"].text == MOCK_TEXT
    fake_sleep.assert_called_once()


def test_stream_failure_after_content_is_not_replayed(no_cost: None) -> None:
    """A drop after content started surfaces immediately.

    Replaying would re-run a generation that may already have run for minutes.
    """
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6", max_retries=2)
    chunks = _mock_chunks("anthropic/claude-sonnet-4-6")
    fake, calls = _failing_then_ok(chunks, fail_after=2, error=_timeout())

    with (
        patch.object(llm_module.litellm, "completion", fake),
        pytest.raises(llm_module.LLMError) as exc_info,
    ):
        llm.complete("hi")

    assert len(calls) == 1
    assert "timed out" in str(exc_info.value)


def test_stream_non_retryable_error_is_not_retried(no_cost: None) -> None:
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6", max_retries=2)
    chunks = _mock_chunks("anthropic/claude-sonnet-4-6")
    error = litellm.AuthenticationError(
        message="invalid x-api-key", model="claude-sonnet-4-6", llm_provider="anthropic"
    )
    fake, calls = _failing_then_ok(chunks, fail_after=0, error=error)

    with (
        patch.object(llm_module.litellm, "completion", fake),
        pytest.raises(llm_module.LLMError),
    ):
        llm.complete("hi")

    assert len(calls) == 1


def test_empty_stream_raises_llm_error(no_cost: None) -> None:
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6")

    def empty(**_: object) -> Iterator[object]:
        yield from ()

    with (
        patch.object(llm_module.litellm, "completion", empty),
        pytest.raises(llm_module.LLMError),
    ):
        llm.complete("hi")


# ── Per-adapter ``enable_streaming`` switch ──────────────────────────────────


def _stream_flag_sent(llm: object) -> bool:
    llm_module = _load_llm_module()
    spy = _Spy()
    with patch.object(llm_module.litellm, "completion", spy):
        llm.complete("hi")
    return bool(spy.calls[0].get("stream"))


def test_anthropic_adapter_can_opt_out_of_streaming(no_cost: None) -> None:
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6", enable_streaming=False)
    assert _stream_flag_sent(llm) is False


def test_openai_adapter_streams_by_default(no_cost: None) -> None:
    llm = _make_llm(OPENAI_ADAPTER_ID, "gpt-4o", api_base="https://api.openai.com/v1")
    assert _stream_flag_sent(llm) is True


def test_missing_flag_streams_for_every_provider(no_cost: None) -> None:
    """Adapters stored before the field existed stream like new ones."""
    anthropic = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6")
    openai = _make_llm(OPENAI_ADAPTER_ID, "gpt-4o", api_base="https://api.openai.com/v1")
    assert _stream_flag_sent(anthropic) is True
    assert _stream_flag_sent(openai) is True


def test_streaming_flag_never_reaches_litellm(no_cost: None) -> None:
    llm_module = _load_llm_module()
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6", enable_streaming=True)
    spy = _Spy()
    with patch.object(llm_module.litellm, "completion", spy):
        llm.complete("hi")
    assert "enable_streaming" not in spy.calls[0]


def test_mocked_completion_keeps_non_streaming_path(
    no_cost: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The e2e rig counts LLM calls via litellm's fixed mock usage (10/20/30).

    That usage is only reported on the non-streaming mock path, and a mock
    never touches the network, so an injected mock response must bypass
    streaming even when the adapter streams.
    """
    llm_module = _load_llm_module()
    monkeypatch.setenv(llm_module._MOCK_RESPONSE_ENV, "canned answer")
    llm = _make_llm(ANTHROPIC_ADAPTER_ID, "claude-sonnet-4-6")
    spy = _Spy()

    with patch.object(llm_module.litellm, "completion", spy):
        result = llm.complete("hi")

    assert spy.calls[0]["mock_response"] == "canned answer"
    assert not spy.calls[0].get("stream")
    assert result["response"].raw["usage"]["prompt_tokens"] == 10
    assert result["response"].raw["usage"]["completion_tokens"] == 20
