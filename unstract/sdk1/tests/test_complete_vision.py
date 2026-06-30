"""Tests for LLM.complete_vision() method."""

from typing import Self
from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.exceptions import LLMError
from unstract.sdk1.llm import LLM
from unstract.sdk1.utils.common import LLMResponseCompat


def _make_llm() -> LLM:
    """Create an LLM instance with mocked internals (bypassing __init__)."""
    llm = object.__new__(LLM)

    # Adapter
    llm.adapter = MagicMock()
    llm.adapter.get_provider.return_value = "test-provider"
    llm.adapter.validate.side_effect = lambda kwargs: kwargs

    # LLM kwargs
    llm.kwargs = {"model": "test-vision-model"}
    llm._cost_model = None
    llm._adapter_name = "Test Adapter"

    # Metrics — capture_metrics decorator checks these
    llm._capture_metrics = False
    llm._run_id = None
    llm._metrics = {}

    # Usage recording
    llm._record_usage = MagicMock()
    llm._pending_usage = []

    return llm


def _make_litellm_response(
    content: str = "extracted value",
    finish_reason: str = "stop",
    usage: dict | None = None,
) -> dict:
    """Build a mock litellm.completion() response dict."""
    return {
        "choices": [
            {
                "message": {"content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage or {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
        },
    }


class TestCompleteVision:
    """Tests for LLM.complete_vision()."""

    @patch("unstract.sdk1.llm.litellm.completion")
    @patch("unstract.sdk1.llm.pop_litellm_retry_kwargs", return_value=0)
    def test_returns_response_compat(
        self: Self,
        _mock_pop: MagicMock,
        mock_completion: MagicMock,
    ) -> None:
        """Should return dict with 'response' key containing LLMResponseCompat."""
        mock_completion.return_value = _make_litellm_response("answer")
        llm = _make_llm()

        messages = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]}
        ]
        result = llm.complete_vision(messages)

        assert "response" in result
        assert isinstance(result["response"], LLMResponseCompat)
        assert result["response"].text == "answer"

    @patch("unstract.sdk1.llm.litellm.completion")
    @patch("unstract.sdk1.llm.pop_litellm_retry_kwargs", return_value=0)
    def test_messages_passed_to_litellm(
        self: Self,
        _mock_pop: MagicMock,
        mock_completion: MagicMock,
    ) -> None:
        """Messages should be forwarded to litellm.completion()."""
        mock_completion.return_value = _make_litellm_response()
        llm = _make_llm()

        messages = [
            {"role": "system", "content": "sys prompt"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "context"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,AAAA"
                        },
                    },
                ],
            },
        ]
        llm.complete_vision(messages)

        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args
        assert call_kwargs.kwargs["messages"] is messages

    @patch("unstract.sdk1.llm.litellm.completion")
    @patch("unstract.sdk1.llm.pop_litellm_retry_kwargs", return_value=0)
    def test_usage_recorded(
        self: Self,
        _mock_pop: MagicMock,
        mock_completion: MagicMock,
    ) -> None:
        """Usage data should be recorded via _record_usage."""
        usage = {
            "prompt_tokens": 500,
            "completion_tokens": 50,
            "total_tokens": 550,
        }
        mock_completion.return_value = _make_litellm_response(
            usage=usage
        )
        llm = _make_llm()

        messages = [
            {"role": "user", "content": [{"type": "text", "text": "q"}]}
        ]
        llm.complete_vision(messages)

        llm._record_usage.assert_called_once()
        call_args = llm._record_usage.call_args
        assert call_args.args[0] == "test-vision-model"  # model
        assert call_args.args[2] == usage  # usage dict
        assert call_args.args[3] == "complete_vision"  # llm_api

    @patch("unstract.sdk1.llm.litellm.completion")
    @patch("unstract.sdk1.llm.pop_litellm_retry_kwargs", return_value=0)
    def test_extract_json_strips_markers(
        self: Self,
        _mock_pop: MagicMock,
        mock_completion: MagicMock,
    ) -> None:
        """extract_json=True should strip JSON code markers."""
        json_response = '```json\n{"key": "value"}\n```'
        mock_completion.return_value = _make_litellm_response(
            content=json_response
        )
        llm = _make_llm()

        messages = [
            {"role": "user", "content": [{"type": "text", "text": "q"}]}
        ]
        result = llm.complete_vision(messages, extract_json=True)

        # After extract_json, the markers should be stripped
        response_text = result["response"].text
        assert "```" not in response_text

    @patch("unstract.sdk1.llm.litellm.completion")
    @patch("unstract.sdk1.llm.pop_litellm_retry_kwargs", return_value=0)
    def test_none_response_raises_llm_error(
        self: Self,
        _mock_pop: MagicMock,
        mock_completion: MagicMock,
    ) -> None:
        """None response content should raise LLMError."""
        mock_completion.return_value = _make_litellm_response(
            content=None, finish_reason="content_filter"
        )
        llm = _make_llm()

        messages = [
            {"role": "user", "content": [{"type": "text", "text": "q"}]}
        ]
        with pytest.raises(LLMError):
            llm.complete_vision(messages)

    @patch("unstract.sdk1.llm.litellm.completion")
    @patch("unstract.sdk1.llm.pop_litellm_retry_kwargs", return_value=0)
    def test_exception_wrapped_in_llm_error(
        self: Self,
        _mock_pop: MagicMock,
        mock_completion: MagicMock,
    ) -> None:
        """Non-LLM exceptions should be wrapped in LLMError."""
        mock_completion.side_effect = RuntimeError("provider error")
        llm = _make_llm()

        messages = [
            {"role": "user", "content": [{"type": "text", "text": "q"}]}
        ]
        with pytest.raises(LLMError, match="Error from LLM adapter"):
            llm.complete_vision(messages)

    @patch("unstract.sdk1.llm.litellm.completion")
    @patch("unstract.sdk1.llm.pop_litellm_retry_kwargs", return_value=0)
    def test_llm_error_reraised_as_is(
        self: Self,
        _mock_pop: MagicMock,
        mock_completion: MagicMock,
    ) -> None:
        """LLMError from the call should be re-raised without wrapping."""
        original_err = LLMError(message="original error")
        mock_completion.side_effect = original_err
        llm = _make_llm()

        messages = [
            {"role": "user", "content": [{"type": "text", "text": "q"}]}
        ]
        with pytest.raises(LLMError) as exc_info:
            llm.complete_vision(messages)
        assert exc_info.value is original_err

    @patch("unstract.sdk1.llm.litellm.completion")
    @patch("unstract.sdk1.llm.pop_litellm_retry_kwargs", return_value=0)
    def test_raw_response_attached(
        self: Self,
        _mock_pop: MagicMock,
        mock_completion: MagicMock,
    ) -> None:
        """Raw litellm response should be attached to response_object.raw."""
        raw_resp = _make_litellm_response("text")
        mock_completion.return_value = raw_resp
        llm = _make_llm()

        messages = [
            {"role": "user", "content": [{"type": "text", "text": "q"}]}
        ]
        result = llm.complete_vision(messages)

        assert result["response"].raw is raw_resp
