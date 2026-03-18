"""Unit tests for RetrieverLLM bridge class and BaseRetriever.llm property."""

import sys
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
    llm.get_model_name.return_value = "gpt-4"
    llm.platform_kwargs = {"run_id": "test-run"}
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


# ── BaseRetriever.llm property tests ────────────────────────────────────────
# BaseRetriever imports VectorDB which triggers the full adapter registration
# chain (Pinecone, Milvus, etc.). We stub unstract.sdk1.vector_db in
# sys.modules so that BaseRetriever can be imported without those heavy deps.


@pytest.fixture
def _stub_vector_db():
    """Temporarily stub VectorDB module for BaseRetriever import."""
    stub = MagicMock()
    key = "unstract.sdk1.vector_db"
    original = sys.modules.get(key)
    sys.modules[key] = stub
    # Also ensure the base_retriever module is re-imported with the stub.
    mod_key = (
        "unstract.prompt_service.core.retrievers.base_retriever"
    )
    sys.modules.pop(mod_key, None)
    yield stub
    # Restore original module (or remove stub).
    if original is not None:
        sys.modules[key] = original
    else:
        sys.modules.pop(key, None)
    sys.modules.pop(mod_key, None)


@pytest.fixture
def base_retriever_cls(_stub_vector_db):
    """Import and return BaseRetriever with VectorDB stubbed."""
    from unstract.prompt_service.core.retrievers.base_retriever import (
        BaseRetriever,
    )

    return BaseRetriever


class TestBaseRetrieverLlmProperty:
    """Tests for BaseRetriever.llm lazy property."""

    def test_returns_none_when_no_llm_provided(
        self, base_retriever_cls
    ):
        """llm property should return None when constructed without LLM."""
        retriever = base_retriever_cls(
            vector_db=MagicMock(),
            prompt="test",
            doc_id="doc-1",
            top_k=5,
        )
        assert retriever.llm is None

    def test_returns_retriever_llm_instance(
        self, base_retriever_cls, mock_sdk1_llm
    ):
        """llm property should return a RetrieverLLM wrapping SDK1 LLM."""
        with patch.object(LLMCompat, "from_llm", return_value=MagicMock()):
            retriever = base_retriever_cls(
                vector_db=MagicMock(),
                prompt="test",
                doc_id="doc-1",
                top_k=5,
                llm=mock_sdk1_llm,
            )
            result = retriever.llm

            assert isinstance(result, RetrieverLLM)
            assert isinstance(result, LlamaIndexBaseLLM)

    def test_lazily_creates_retriever_llm(
        self, base_retriever_cls, mock_sdk1_llm
    ):
        """RetrieverLLM should not be created until .llm is accessed."""
        retriever = base_retriever_cls(
            vector_db=MagicMock(),
            prompt="test",
            doc_id="doc-1",
            top_k=5,
            llm=mock_sdk1_llm,
        )
        # Before accessing .llm, the internal cache should be None.
        assert retriever._retriever_llm is None

        with patch.object(LLMCompat, "from_llm", return_value=MagicMock()):
            _ = retriever.llm

        # After access, it should be populated.
        assert retriever._retriever_llm is not None

    def test_caches_retriever_llm_across_accesses(
        self, base_retriever_cls, mock_sdk1_llm
    ):
        """Repeated .llm accesses should return the same instance."""
        with patch.object(LLMCompat, "from_llm", return_value=MagicMock()):
            retriever = base_retriever_cls(
                vector_db=MagicMock(),
                prompt="test",
                doc_id="doc-1",
                top_k=5,
                llm=mock_sdk1_llm,
            )
            first = retriever.llm
            second = retriever.llm

            assert first is second

    def test_from_llm_called_once_on_repeated_access(
        self, base_retriever_cls, mock_sdk1_llm
    ):
        """LLMCompat.from_llm should only be called once across accesses."""
        with patch.object(
            LLMCompat, "from_llm", return_value=MagicMock()
        ) as mock_factory:
            retriever = base_retriever_cls(
                vector_db=MagicMock(),
                prompt="test",
                doc_id="doc-1",
                top_k=5,
                llm=mock_sdk1_llm,
            )
            _ = retriever.llm
            _ = retriever.llm
            _ = retriever.llm

            mock_factory.assert_called_once()

    def test_raw_llm_still_accessible(
        self, base_retriever_cls, mock_sdk1_llm
    ):
        """The raw SDK1 LLM should remain accessible via _llm."""
        retriever = base_retriever_cls(
            vector_db=MagicMock(),
            prompt="test",
            doc_id="doc-1",
            top_k=5,
            llm=mock_sdk1_llm,
        )
        assert retriever._llm is mock_sdk1_llm


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
