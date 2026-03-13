"""Unit tests for LLMCompat, emulated types, and _to_litellm_messages."""

from typing import Self
from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.llm import (
    LLM,
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    LLMCompat,
    LLMMetadata,
    MessageRole,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_sdk1_llm() -> MagicMock:
    """Create a mock SDK1 LLM instance with adapter attributes."""
    llm = MagicMock(spec=LLM)
    llm._adapter_id = "openai"
    llm._adapter_metadata = {"api_key": "test-key"}
    llm._adapter_instance_id = "inst-123"
    llm._tool = MagicMock()
    llm._usage_kwargs = {"run_id": "test-run"}
    llm._capture_metrics = False
    return llm


# ── LLMCompat.from_llm tests ────────────────────────────────────────────────


class TestLLMCompatFromLlm:
    """Tests for the LLMCompat.from_llm factory method."""

    @patch.object(LLMCompat, "__init__", return_value=None)
    def test_from_llm_passes_adapter_params(
        self: Self, mock_init: MagicMock, mock_sdk1_llm: MagicMock
    ) -> None:
        """Verify from_llm extracts and forwards all adapter params."""
        LLMCompat.from_llm(mock_sdk1_llm)

        mock_init.assert_called_once_with(
            adapter_id="openai",
            adapter_metadata={"api_key": "test-key"},
            adapter_instance_id="inst-123",
            tool=mock_sdk1_llm._tool,
            usage_kwargs={"run_id": "test-run"},
            capture_metrics=False,
        )

    @patch.object(LLMCompat, "__init__", return_value=None)
    def test_from_llm_returns_llmcompat_instance(
        self: Self, mock_init: MagicMock, mock_sdk1_llm: MagicMock
    ) -> None:
        """Verify from_llm returns an LLMCompat instance."""
        result = LLMCompat.from_llm(mock_sdk1_llm)
        assert isinstance(result, LLMCompat)


# ── Emulated types tests ────────────────────────────────────────────────────


class TestEmulatedTypes:
    """Tests for the emulated llama-index types in SDK1."""

    def test_message_role_values(self: Self) -> None:
        """Emulated MessageRole should have correct string values."""
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.FUNCTION.value == "function"
        assert MessageRole.TOOL.value == "tool"

    def test_chat_message_defaults(self: Self) -> None:
        """ChatMessage should default to USER role with None content."""
        msg = ChatMessage()
        assert msg.role == MessageRole.USER
        assert msg.content is None

    def test_chat_response_message_access(self: Self) -> None:
        """ChatResponse.message.content should be accessible."""
        resp = ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content="test")
        )
        assert resp.message.content == "test"
        assert resp.message.role == MessageRole.ASSISTANT

    def test_completion_response_text(self: Self) -> None:
        """CompletionResponse.text should be accessible."""
        resp = CompletionResponse(text="completed")
        assert resp.text == "completed"

    def test_llm_metadata_defaults(self: Self) -> None:
        """LLMMetadata should default to chat model."""
        meta = LLMMetadata()
        assert meta.is_chat_model is True
        assert meta.model_name == ""


# ── _to_litellm_messages tests ──────────────────────────────────────────────


class TestToLitellmMessages:
    """Tests for LLMCompat._to_litellm_messages role conversion."""

    def test_emulated_message_role(self: Self) -> None:
        """Should handle emulated MessageRole enum."""
        messages = [ChatMessage(role=MessageRole.USER, content="hello")]
        result = LLMCompat._to_litellm_messages(messages)
        assert result == [{"role": "user", "content": "hello"}]

    def test_none_content_becomes_empty_string(self: Self) -> None:
        """None content should be converted to empty string."""
        messages = [ChatMessage(role=MessageRole.USER, content=None)]
        result = LLMCompat._to_litellm_messages(messages)
        assert result == [{"role": "user", "content": ""}]

    def test_multiple_messages(self: Self) -> None:
        """Should handle multiple messages in sequence."""
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content="You are helpful"),
            ChatMessage(role=MessageRole.USER, content="Hi"),
            ChatMessage(role=MessageRole.ASSISTANT, content="Hello"),
        ]
        result = LLMCompat._to_litellm_messages(messages)
        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "assistant"

    def test_string_role_fallback(self: Self) -> None:
        """Should handle non-enum role via getattr fallback."""
        msg = MagicMock()
        msg.role = "custom_role"
        msg.content = "test"
        result = LLMCompat._to_litellm_messages([msg])
        assert result == [{"role": "custom_role", "content": "test"}]
