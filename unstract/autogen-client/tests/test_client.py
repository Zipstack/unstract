"""Tests for UnstractAutoGenClient."""

from unittest.mock import Mock

import pytest
from autogen_core.models import (
    ModelInfo,
    RequestUsage,
    SystemMessage,
    UserMessage,
)
from unstract.autogen_client import (
    UnstractAutoGenClient,
    UnstractCompletionError,
    UnstractConfigurationError,
)


class TestUnstractAutoGenClient:
    """Test cases for UnstractAutoGenClient."""

    @pytest.fixture
    def mock_adapter(self) -> Mock:
        """Create a mock Unstract LLM adapter."""
        adapter = Mock()
        adapter.completion = Mock()
        return adapter

    @pytest.fixture
    def mock_response(self) -> Mock:
        """Create a mock adapter response."""
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.choices[0].message.content = "Test response"
        response.choices[0].finish_reason = "stop"
        response.usage = Mock()
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 5
        response.usage.total_tokens = 15
        return response

    @pytest.fixture
    def client(self, mock_adapter: Mock) -> UnstractAutoGenClient:
        """Create a test client."""
        return UnstractAutoGenClient(
            llm_adapter=mock_adapter,
            timeout=30.0,
            enable_retries=False,  # Disable for simpler testing
        )

    def test_initialization(self, mock_adapter: Mock) -> None:
        """Test client initialization."""
        client = UnstractAutoGenClient(
            llm_adapter=mock_adapter,
            timeout=30.0,
            max_retries=5,
        )

        assert client.llm_adapter == mock_adapter
        assert client._timeout == 30.0
        assert client._max_retries == 5

    def test_initialization_validation(self) -> None:
        """Test validation during initialization."""
        # Test that adapter must be provided
        with pytest.raises(
            UnstractConfigurationError, match="llm_adapter must be provided"
        ):
            UnstractAutoGenClient(llm_adapter=None)

        # Test that adapter must have completion method
        mock_adapter = Mock()
        delattr(mock_adapter, "completion") if hasattr(
            mock_adapter, "completion"
        ) else None
        with pytest.raises(
            UnstractConfigurationError,
            match="llm_adapter must have a 'completion' method",
        ):
            UnstractAutoGenClient(llm_adapter=mock_adapter)

    def test_model_info_property(self, client: UnstractAutoGenClient) -> None:
        """Test model_info property."""
        model_info = client.model_info
        assert isinstance(model_info, ModelInfo)
        assert model_info.supports_streaming is True
        assert model_info.family == "unstract"

    def test_capabilities(self, client: UnstractAutoGenClient) -> None:
        """Test capabilities method."""
        capabilities = client.capabilities()

        expected_capabilities = {
            "chat": True,
            "stream": True,
            "count_tokens": True,
            "function_calling": True,
            "vision": True,
            "json_output": True,
        }

        assert capabilities == expected_capabilities

    @pytest.mark.asyncio
    async def test_create_completion(
        self, client: UnstractAutoGenClient, mock_adapter: Mock, mock_response: Mock
    ) -> None:
        """Test create completion method."""
        mock_adapter.completion.return_value = mock_response

        messages = [UserMessage(content="Hello", source="user")]
        result = await client.create(messages)

        assert result.content == "Test response"
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert result.finish_reason == "stop"

        # Verify adapter was called with normalized messages
        mock_adapter.completion.assert_called_once()
        call_args = mock_adapter.completion.call_args[1]
        assert "messages" in call_args
        assert call_args["messages"][0]["role"] == "user"
        assert call_args["messages"][0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_create_completion_with_mixed_messages(
        self, client: UnstractAutoGenClient, mock_adapter: Mock, mock_response: Mock
    ) -> None:
        """Test create completion with mixed message types."""
        mock_adapter.completion.return_value = mock_response

        messages = [
            SystemMessage(content="You are helpful", source="system"),
            UserMessage(content="Hello", source="user"),
            {"role": "assistant", "content": "Hi there"},
        ]

        result = await client.create(messages)

        # Verify message normalization
        call_args = mock_adapter.completion.call_args[1]
        normalized_messages = call_args["messages"]

        assert len(normalized_messages) == 3
        assert normalized_messages[0]["role"] == "system"
        assert normalized_messages[0]["content"] == "You are helpful"
        assert normalized_messages[1]["role"] == "user"
        assert normalized_messages[1]["content"] == "Hello"
        assert normalized_messages[2]["role"] == "assistant"
        assert normalized_messages[2]["content"] == "Hi there"

    @pytest.mark.asyncio
    async def test_create_completion_error_handling(
        self, client: UnstractAutoGenClient, mock_adapter: Mock
    ) -> None:
        """Test error handling in create completion."""
        mock_adapter.completion.side_effect = Exception("Adapter failed")

        messages = [UserMessage(content="Hello", source="user")]

        with pytest.raises(
            UnstractCompletionError, match="Unstract adapter completion failed"
        ):
            await client.create(messages)

    @pytest.mark.asyncio
    async def test_closed_client_error(self, client: UnstractAutoGenClient) -> None:
        """Test that closed client raises error."""
        await client.close()

        messages = [UserMessage(content="Hello", source="user")]

        with pytest.raises(UnstractCompletionError, match="Client has been closed"):
            await client.create(messages)

    def test_count_tokens(self, client: UnstractAutoGenClient) -> None:
        """Test token counting."""
        messages = [
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there how are you"},
        ]

        token_count = client.count_tokens(messages)
        assert token_count > 0
        assert token_count == 7  # "Hello world Hi there how are you" = 7 words

    def test_remaining_tokens_unknown_max(self, client: UnstractAutoGenClient) -> None:
        """Test remaining tokens when max is unknown."""
        remaining = client.remaining_tokens()
        assert remaining == -1  # Unknown max tokens

    def test_remaining_tokens_with_max(self, mock_adapter: Mock) -> None:
        """Test remaining tokens with known max."""
        model_info = ModelInfo(
            family="unstract",
            vision=False,
            function_calling=False,
            json_output=False,
            max_tokens=1000,
            supports_streaming=True,
        )

        client = UnstractAutoGenClient(llm_adapter=mock_adapter, model_info=model_info)

        # Set some usage
        client._last_usage = RequestUsage(prompt_tokens=100, completion_tokens=50)

        remaining = client.remaining_tokens()
        assert remaining == 850  # 1000 - 100 - 50

    def test_usage_tracking(self, client: UnstractAutoGenClient) -> None:
        """Test usage tracking functionality."""
        # Initial usage should be zero
        assert client.total_usage().prompt_tokens == 0
        assert client.total_usage().completion_tokens == 0
        assert client.actual_usage().prompt_tokens == 0
        assert client.actual_usage().completion_tokens == 0

    @pytest.mark.asyncio
    async def test_usage_accumulation(
        self, client: UnstractAutoGenClient, mock_adapter: Mock, mock_response: Mock
    ) -> None:
        """Test that usage accumulates across requests."""
        mock_adapter.completion.return_value = mock_response

        # First request
        messages = [UserMessage(content="Hello", source="user")]
        await client.create(messages)

        assert client.total_usage().prompt_tokens == 10
        assert client.total_usage().completion_tokens == 5
        assert client.actual_usage().prompt_tokens == 10
        assert client.actual_usage().completion_tokens == 5

        # Second request
        await client.create(messages)

        assert client.total_usage().prompt_tokens == 20  # Accumulated
        assert client.total_usage().completion_tokens == 10  # Accumulated
        assert client.actual_usage().prompt_tokens == 10  # Last request only
        assert client.actual_usage().completion_tokens == 5  # Last request only

    @pytest.mark.asyncio
    async def test_create_stream_placeholder(
        self, client: UnstractAutoGenClient, mock_adapter: Mock
    ) -> None:
        """Test create_stream method (basic functionality)."""
        # Mock streaming response
        mock_chunks = [Mock(), Mock()]
        mock_chunks[0].choices = [Mock()]
        mock_chunks[0].choices[0].delta = Mock()
        mock_chunks[0].choices[0].delta.content = "Hello "
        mock_chunks[1].choices = [Mock()]
        mock_chunks[1].choices[0].delta = Mock()
        mock_chunks[1].choices[0].delta.content = "world"

        # Mock the streaming call to return the chunks
        def mock_streaming_completion(**kwargs):
            return iter(mock_chunks)

        # Mock the final call for usage info
        final_response = Mock()
        final_response.usage = Mock()
        final_response.usage.prompt_tokens = 2
        final_response.usage.completion_tokens = 2
        final_response.choices = [Mock()]
        final_response.choices[0].finish_reason = "stop"

        def mock_completion(**kwargs):
            if kwargs.get("stream"):
                return mock_streaming_completion(**kwargs)
            else:
                return final_response

        mock_adapter.completion.side_effect = mock_completion

        messages = [UserMessage(content="Hi", source="user")]

        chunks = []
        final_result = None

        async for item in client.create_stream(messages):
            if isinstance(item, str):
                chunks.append(item)
            else:
                final_result = item

        assert chunks == ["Hello ", "world"]
        assert final_result is not None
        assert final_result.content == "Hello world"
        assert final_result.usage.prompt_tokens == 2
        assert final_result.usage.completion_tokens == 2
