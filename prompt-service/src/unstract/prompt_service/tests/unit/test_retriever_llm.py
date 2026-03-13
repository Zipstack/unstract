"""Unit tests for RetrieverLLM bridge class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    LLMMetadata,
    MessageRole,
)
from llama_index.core.llms.llm import LLM as LlamaIndexBaseLLM  # noqa: N811
from unstract.prompt_service.core.retrievers.retriever_llm import RetrieverLLM
from unstract.sdk1.llm import LLM, LLMCompat
from unstract.sdk1.llm import ChatMessage as EmulatedChatMessage
from unstract.sdk1.llm import ChatResponse as EmulatedChatResponse
from unstract.sdk1.llm import CompletionResponse as EmulatedCompletionResponse
from unstract.sdk1.llm import LLMMetadata as EmulatedLLMMetadata
from unstract.sdk1.llm import MessageRole as EmulatedMessageRole

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_sdk1_llm():
    """Create a mock SDK1 LLM instance with adapter attributes."""
    llm = MagicMock(spec=LLM)
    llm._adapter_id = "openai"
    llm._adapter_metadata = {"api_key": "test-key"}
    llm._adapter_instance_id = "inst-123"
    llm._tool = MagicMock()
    llm._usage_kwargs = {"run_id": "test-run"}
    llm._capture_metrics = False
    return llm


@pytest.fixture
def mock_compat():
    """Create a mock LLMCompat instance."""
    compat = MagicMock(spec=LLMCompat)
    compat.get_model_name.return_value = "gpt-4"
    compat.metadata = EmulatedLLMMetadata(
        is_chat_model=True, model_name="gpt-4"
    )
    return compat


# ── RetrieverLLM tests ───────────────────────────────────────────────────────


class TestRetrieverLLM:
    """Tests for the RetrieverLLM bridge class."""

    def test_isinstance_llama_index_llm(self, mock_sdk1_llm):
        """RetrieverLLM must pass llama-index's isinstance check."""
        with patch.object(LLMCompat, "from_llm", return_value=MagicMock()):
            retriever_llm = RetrieverLLM(llm=mock_sdk1_llm)
            assert isinstance(retriever_llm, LlamaIndexBaseLLM)

    def test_uses_from_llm_factory(self, mock_sdk1_llm):
        """RetrieverLLM should use LLMCompat.from_llm, not private attrs."""
        with patch.object(
            LLMCompat, "from_llm", return_value=MagicMock()
        ) as mock_factory:
            RetrieverLLM(llm=mock_sdk1_llm)
            mock_factory.assert_called_once_with(mock_sdk1_llm)

    def test_metadata_returns_llama_index_type(
        self, mock_sdk1_llm, mock_compat
    ):
        """Metadata property should return llama-index LLMMetadata."""
        with patch.object(LLMCompat, "from_llm", return_value=mock_compat):
            retriever_llm = RetrieverLLM(llm=mock_sdk1_llm)
            meta = retriever_llm.metadata
            assert isinstance(meta, LLMMetadata)
            assert meta.is_chat_model is True
            assert meta.model_name == "gpt-4"

    def test_chat_delegates_and_converts_types(
        self, mock_sdk1_llm, mock_compat
    ):
        """chat() should delegate to compat and return llama-index types."""
        mock_compat.chat.return_value = EmulatedChatResponse(
            message=EmulatedChatMessage(
                role=EmulatedMessageRole.ASSISTANT,
                content="Hello from LLM",
            ),
            raw={"id": "resp-1"},
        )
        with patch.object(LLMCompat, "from_llm", return_value=mock_compat):
            retriever_llm = RetrieverLLM(llm=mock_sdk1_llm)
            messages = [
                ChatMessage(role=MessageRole.USER, content="Hi")
            ]
            result = retriever_llm.chat(messages)

            assert isinstance(result, ChatResponse)
            assert result.message.content == "Hello from LLM"
            assert result.raw == {"id": "resp-1"}
            mock_compat.chat.assert_called_once()

    def test_complete_delegates_and_converts_types(
        self, mock_sdk1_llm, mock_compat
    ):
        """complete() should delegate to compat and return llama-index types."""
        mock_compat.complete.return_value = EmulatedCompletionResponse(
            text="Completed text", raw={"id": "resp-2"}
        )
        with patch.object(LLMCompat, "from_llm", return_value=mock_compat):
            retriever_llm = RetrieverLLM(llm=mock_sdk1_llm)
            result = retriever_llm.complete("Test prompt")

            assert isinstance(result, CompletionResponse)
            assert result.text == "Completed text"
            assert result.raw == {"id": "resp-2"}
            mock_compat.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_achat_delegates_and_converts_types(
        self, mock_sdk1_llm, mock_compat
    ):
        """achat() should delegate to compat and return llama-index types."""
        mock_compat.achat = AsyncMock(
            return_value=EmulatedChatResponse(
                message=EmulatedChatMessage(
                    role=EmulatedMessageRole.ASSISTANT,
                    content="Async hello",
                ),
                raw={"id": "resp-3"},
            )
        )
        with patch.object(LLMCompat, "from_llm", return_value=mock_compat):
            retriever_llm = RetrieverLLM(llm=mock_sdk1_llm)
            messages = [
                ChatMessage(role=MessageRole.USER, content="Hi async")
            ]
            result = await retriever_llm.achat(messages)

            assert isinstance(result, ChatResponse)
            assert result.message.content == "Async hello"

    @pytest.mark.asyncio
    async def test_acomplete_delegates_and_converts_types(
        self, mock_sdk1_llm, mock_compat
    ):
        """acomplete() should delegate to compat and return llama-index types."""
        mock_compat.acomplete = AsyncMock(
            return_value=EmulatedCompletionResponse(
                text="Async completed", raw={"id": "resp-4"}
            )
        )
        with patch.object(LLMCompat, "from_llm", return_value=mock_compat):
            retriever_llm = RetrieverLLM(llm=mock_sdk1_llm)
            result = await retriever_llm.acomplete("Async prompt")

            assert isinstance(result, CompletionResponse)
            assert result.text == "Async completed"

    def test_stream_chat_not_implemented(self, mock_sdk1_llm):
        """stream_chat() should raise NotImplementedError."""
        with patch.object(LLMCompat, "from_llm", return_value=MagicMock()):
            retriever_llm = RetrieverLLM(llm=mock_sdk1_llm)
            with pytest.raises(NotImplementedError):
                retriever_llm.stream_chat([])

    def test_stream_complete_not_implemented(self, mock_sdk1_llm):
        """stream_complete() should raise NotImplementedError."""
        with patch.object(LLMCompat, "from_llm", return_value=MagicMock()):
            retriever_llm = RetrieverLLM(llm=mock_sdk1_llm)
            with pytest.raises(NotImplementedError):
                retriever_llm.stream_complete("prompt")
