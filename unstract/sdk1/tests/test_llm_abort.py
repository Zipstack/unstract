"""`LLM.complete` abandons a wedged provider call (UN-1031).

The behaviour that matters to a user: pressing Stop while a model is taking
minutes to answer should not mean waiting minutes. These tests stand a slow
provider in for the real thing and assert we stop waiting for it — and,
equally important, that a caller who never aborts is completely unaffected.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.llm import LLM
from unstract.sdk1.utils.aborting import AbortedError, abort_scope


def _fake_response(text: str = "an answer") -> dict:
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


@pytest.fixture
def llm() -> LLM:
    """An LLM with its adapter and bookkeeping stubbed out.

    Constructing a real one needs a platform round trip; everything under test
    here sits between `complete()` and litellm.
    """
    inst = LLM.__new__(LLM)
    inst.adapter = MagicMock()
    inst.adapter.validate.return_value = {"model": "test/model", "max_retries": 2}
    inst.adapter.get_provider.return_value = "test"
    inst.kwargs = {"model": "test/model"}
    inst._cost_model = None
    inst._enable_prompt_caching = False
    inst._prompt_caching_active = MagicMock(return_value=False)
    inst._system_prompt = None
    inst._record_usage = MagicMock()
    inst._get_adapter_info = MagicMock(return_value="test adapter")
    return inst


class TestAbortableCompletion:
    def test_a_wedged_call_is_abandoned_promptly(self, llm: LLM) -> None:
        """The whole point: a slow provider must not hold the caller."""

        async def never_returns(**_kwargs: object) -> dict:
            await asyncio.sleep(30)
            return _fake_response()

        started = time.monotonic()
        with (
            patch("litellm.acompletion", side_effect=never_returns),
            abort_scope(lambda: True),
            pytest.raises(AbortedError),
        ):
            llm.complete("what is on page 7?")
        elapsed = time.monotonic() - started

        assert elapsed < 5, f"waited {elapsed:.1f}s for an abandoned call"

    def test_an_abort_is_not_reported_as_a_provider_failure(self, llm: LLM) -> None:
        """A stop is not a provider failure.

        `complete` wraps provider errors in LLMError, and callers match on the
        type to tell the two apart.
        """

        async def never_returns(**_kwargs: object) -> None:
            await asyncio.sleep(30)

        with (
            patch("litellm.acompletion", side_effect=never_returns),
            abort_scope(lambda: True),
        ):
            with pytest.raises(AbortedError):
                llm.complete("prompt")

    def test_an_unaborted_call_returns_normally(self, llm: LLM) -> None:
        async def answers(**_kwargs: object) -> dict:
            return _fake_response("42")

        with (
            patch("litellm.acompletion", side_effect=answers),
            abort_scope(lambda: False),
        ):
            result = llm.complete("prompt")

        assert result["response"].text == "42"

    def test_a_provider_error_still_surfaces_as_an_llm_error(self, llm: LLM) -> None:
        from unstract.sdk1.exceptions import LLMError

        async def explodes(**_kwargs: object) -> None:
            raise ValueError("model not found")

        with (
            patch("litellm.acompletion", side_effect=explodes),
            abort_scope(lambda: False),
            pytest.raises(LLMError),
        ):
            llm.complete("prompt")


class TestCallersWithoutAStopButton:
    """Workflow and API-deployment runs must be untouched by all of this."""

    def test_no_abort_scope_uses_the_synchronous_path(self, llm: LLM) -> None:
        with (
            patch("litellm.completion", return_value=_fake_response("sync")) as sync,
            patch("litellm.acompletion") as async_call,
        ):
            result = llm.complete("prompt")

        assert result["response"].text == "sync"
        sync.assert_called_once()
        async_call.assert_not_called()

    def test_an_explicitly_none_scope_uses_the_synchronous_path(self, llm: LLM) -> None:
        with (
            patch("litellm.completion", return_value=_fake_response("sync")) as sync,
            patch("litellm.acompletion") as async_call,
            abort_scope(None),
        ):
            llm.complete("prompt")

        sync.assert_called_once()
        async_call.assert_not_called()


class TestTheSwitch:
    def test_disabling_it_falls_back_to_the_synchronous_call(
        self, llm: LLM, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The escape hatch for a provider that misbehaves on the async path."""
        monkeypatch.setenv("UNSTRACT_LLM_ABORT_INFLIGHT", "false")

        with (
            patch("litellm.completion", return_value=_fake_response("sync")) as sync,
            patch("litellm.acompletion") as async_call,
            abort_scope(lambda: False),
        ):
            llm.complete("prompt")

        sync.assert_called_once()
        async_call.assert_not_called()

    def test_it_is_on_by_default(self, llm: LLM, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNSTRACT_LLM_ABORT_INFLIGHT", raising=False)

        async def answers(**_kwargs: object) -> dict:
            return _fake_response()

        with (
            patch("litellm.acompletion", side_effect=answers) as async_call,
            patch("litellm.completion") as sync,
            abort_scope(lambda: False),
        ):
            llm.complete("prompt")

        async_call.assert_called_once()
        sync.assert_not_called()
