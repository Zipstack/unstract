"""Unit tests for LLMCompat, emulated types, and _messages_to_prompt."""

from typing import Self
from unittest.mock import AsyncMock, MagicMock, patch

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
from unstract.sdk1.utils.common import LLMResponseCompat

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
    llm._system_prompt = ""
    llm._capture_metrics = False
    llm.get_model_name.return_value = "gpt-4"
    llm.platform_kwargs = {"run_id": "test-run"}
    return llm


@pytest.fixture
def compat_from_mock(mock_sdk1_llm: MagicMock) -> LLMCompat:
    """Create an LLMCompat via from_llm() with PlatformHelper mocked."""
    with patch("unstract.sdk1.llm.PlatformHelper") as mock_ph:
        mock_ph.is_public_adapter.return_value = True
        return LLMCompat.from_llm(mock_sdk1_llm)


# ── LLMCompat.from_llm tests ────────────────────────────────────────────────


class TestLLMCompatFromLlm:
    """Tests for the LLMCompat.from_llm factory method."""

    @patch("unstract.sdk1.llm.PlatformHelper")
    def test_from_llm_reuses_llm_instance(
        self: Self,
        mock_platform_helper: MagicMock,
        mock_sdk1_llm: MagicMock,
    ) -> None:
        """Verify from_llm reuses the existing LLM, not re-creating one."""
        mock_platform_helper.is_public_adapter.return_value = True
        result = LLMCompat.from_llm(mock_sdk1_llm)

        assert result._llm_instance is mock_sdk1_llm

    @patch("unstract.sdk1.llm.PlatformHelper")
    def test_from_llm_returns_llmcompat_instance(
        self: Self,
        mock_platform_helper: MagicMock,
        mock_sdk1_llm: MagicMock,
    ) -> None:
        """Verify from_llm returns an LLMCompat instance."""
        mock_platform_helper.is_public_adapter.return_value = True
        result = LLMCompat.from_llm(mock_sdk1_llm)
        assert isinstance(result, LLMCompat)

    @patch("unstract.sdk1.llm.PlatformHelper")
    def test_from_llm_sets_model_name(
        self: Self,
        mock_platform_helper: MagicMock,
        mock_sdk1_llm: MagicMock,
    ) -> None:
        """Verify from_llm sets model_name from the LLM instance."""
        mock_platform_helper.is_public_adapter.return_value = True
        result = LLMCompat.from_llm(mock_sdk1_llm)
        assert result.model_name == "gpt-4"

    @patch("unstract.sdk1.llm.PlatformHelper")
    def test_from_llm_does_not_call_init(
        self: Self,
        mock_platform_helper: MagicMock,
        mock_sdk1_llm: MagicMock,
    ) -> None:
        """Verify from_llm bypasses __init__ (no redundant LLM creation)."""
        mock_platform_helper.is_public_adapter.return_value = True
        with patch.object(LLMCompat, "__init__") as mock_init:
            LLMCompat.from_llm(mock_sdk1_llm)
            mock_init.assert_not_called()


# ── LLMCompat delegation tests ──────────────────────────────────────────────


class TestLLMCompatDelegation:
    """Tests verifying LLMCompat delegates to LLM.complete/acomplete."""

    def _make_llm_response(
        self: Self,
        text: str = "response text",
        raw: object = None,
    ) -> dict[str, object]:
        """Build a dict matching LLM.complete() return shape."""
        resp = LLMResponseCompat(text)
        resp.raw = raw or {"id": "test-resp"}
        return {"response": resp}

    def test_complete_delegates_to_llm(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """complete() should call LLM.complete() and wrap the result."""
        llm_mock = compat_from_mock._llm_instance
        llm_mock.complete.return_value = self._make_llm_response("done", {"id": "r1"})

        result = compat_from_mock.complete("test prompt")

        llm_mock.complete.assert_called_once_with("test prompt")
        assert isinstance(result, CompletionResponse)
        assert result.text == "done"
        assert result.raw == {"id": "r1"}

    def test_chat_delegates_to_llm_complete(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """chat() should flatten messages and delegate to LLM.complete()."""
        llm_mock = compat_from_mock._llm_instance
        llm_mock.complete.return_value = self._make_llm_response(
            "chat reply", {"id": "r2"}
        )

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content="Be helpful"),
            ChatMessage(role=MessageRole.USER, content="Hello"),
        ]
        result = compat_from_mock.chat(messages)

        # Should concatenate all messages with role prefixes.
        expected = "system: Be helpful\nuser: Hello"
        llm_mock.complete.assert_called_once_with(expected)
        assert isinstance(result, ChatResponse)
        assert result.message.role == MessageRole.ASSISTANT
        assert result.message.content == "chat reply"
        assert result.raw == {"id": "r2"}

    def test_chat_forwards_kwargs_to_llm(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """chat() should forward extra kwargs to LLM.complete()."""
        llm_mock = compat_from_mock._llm_instance
        llm_mock.complete.return_value = self._make_llm_response()

        messages = [ChatMessage(role=MessageRole.USER, content="Hi")]
        compat_from_mock.chat(messages, temperature=0.5)

        llm_mock.complete.assert_called_once_with("user: Hi", temperature=0.5)

    def test_complete_forwards_kwargs_to_llm(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """complete() should forward extra kwargs to LLM.complete()."""
        llm_mock = compat_from_mock._llm_instance
        llm_mock.complete.return_value = self._make_llm_response()

        compat_from_mock.complete("prompt", max_tokens=100)

        llm_mock.complete.assert_called_once_with("prompt", max_tokens=100)

    @pytest.mark.asyncio
    async def test_acomplete_delegates_to_llm(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """acomplete() should call LLM.acomplete() and wrap the result."""
        llm_mock = compat_from_mock._llm_instance
        llm_mock.acomplete = AsyncMock(
            return_value=self._make_llm_response("async done", {"id": "r3"})
        )

        result = await compat_from_mock.acomplete("async prompt")

        llm_mock.acomplete.assert_called_once_with("async prompt")
        assert isinstance(result, CompletionResponse)
        assert result.text == "async done"
        assert result.raw == {"id": "r3"}

    @pytest.mark.asyncio
    async def test_achat_delegates_to_llm_acomplete(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """achat() should extract prompt and delegate to LLM.acomplete()."""
        llm_mock = compat_from_mock._llm_instance
        llm_mock.acomplete = AsyncMock(
            return_value=self._make_llm_response("async chat reply", {"id": "r4"})
        )

        messages = [
            ChatMessage(role=MessageRole.USER, content="Async hello"),
        ]
        result = await compat_from_mock.achat(messages)

        llm_mock.acomplete.assert_called_once_with("user: Async hello")
        assert isinstance(result, ChatResponse)
        assert result.message.role == MessageRole.ASSISTANT
        assert result.message.content == "async chat reply"

    def test_stream_chat_not_implemented(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """stream_chat() should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            compat_from_mock.stream_chat([])

    def test_stream_complete_not_implemented(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """stream_complete() should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            compat_from_mock.stream_complete("prompt")

    @pytest.mark.asyncio
    async def test_astream_chat_not_implemented(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """astream_chat() should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await compat_from_mock.astream_chat([])

    @pytest.mark.asyncio
    async def test_astream_complete_not_implemented(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """astream_complete() should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await compat_from_mock.astream_complete("prompt")

    def test_metadata_returns_emulated_type(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """Metadata property should return emulated LLMMetadata."""
        meta = compat_from_mock.metadata
        assert isinstance(meta, LLMMetadata)
        assert meta.is_chat_model is True
        assert meta.model_name == "gpt-4"

    def test_get_model_name_delegates(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """get_model_name() should delegate to LLM instance."""
        assert compat_from_mock.get_model_name() == "gpt-4"
        compat_from_mock._llm_instance.get_model_name.assert_called()

    def test_get_metrics_delegates(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """get_metrics() should delegate to LLM instance."""
        compat_from_mock._llm_instance.get_metrics.return_value = {"time": 1.5}
        assert compat_from_mock.get_metrics() == {"time": 1.5}

    def test_test_connection_delegates(
        self: Self,
        compat_from_mock: LLMCompat,
    ) -> None:
        """test_connection() should delegate to LLM instance."""
        compat_from_mock._llm_instance.test_connection.return_value = True
        assert compat_from_mock.test_connection() is True


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


# ── _messages_to_prompt tests ────────────────────────────────────────────────


class TestMessagesToPrompt:
    """Tests for LLMCompat._messages_to_prompt flattening."""

    def test_single_user_message(self: Self) -> None:
        """Should format a single user message with role prefix."""
        messages = [ChatMessage(role=MessageRole.USER, content="hello")]
        assert LLMCompat._messages_to_prompt(messages) == "user: hello"

    def test_none_content_becomes_empty_string(self: Self) -> None:
        """None content should be converted to empty string."""
        messages = [ChatMessage(role=MessageRole.USER, content=None)]
        assert LLMCompat._messages_to_prompt(messages) == "user: "

    def test_preserves_all_messages(self: Self) -> None:
        """Should concatenate all messages preserving system instructions."""
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content="You are helpful"),
            ChatMessage(role=MessageRole.USER, content="Question"),
        ]
        expected = "system: You are helpful\nuser: Question"
        assert LLMCompat._messages_to_prompt(messages) == expected

    def test_multi_turn_conversation(self: Self) -> None:
        """Should preserve all turns in a multi-turn conversation."""
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content="Be concise"),
            ChatMessage(role=MessageRole.USER, content="First"),
            ChatMessage(role=MessageRole.ASSISTANT, content="Answer"),
            ChatMessage(role=MessageRole.USER, content="Follow-up"),
        ]
        result = LLMCompat._messages_to_prompt(messages)
        assert result == (
            "system: Be concise\n" "user: First\n" "assistant: Answer\n" "user: Follow-up"
        )

    def test_empty_messages_returns_empty_string(self: Self) -> None:
        """Should return empty string for empty message list."""
        assert LLMCompat._messages_to_prompt([]) == ""

    def test_string_role_fallback(self: Self) -> None:
        """Should handle non-enum role via getattr fallback."""
        msg = MagicMock()
        msg.role = "user"
        msg.content = "test"
        assert LLMCompat._messages_to_prompt([msg]) == "user: test"
