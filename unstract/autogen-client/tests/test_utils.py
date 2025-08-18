"""Tests for utility functions."""

from unittest.mock import Mock

import pytest
from autogen_core.models import (
    AssistantMessage,
    FunctionExecutionResultMessage,
    RequestUsage,
    SystemMessage,
    UserMessage,
)
from unstract.autogen_client.utils import (
    estimate_token_count,
    extract_content,
    extract_finish_reason,
    extract_usage,
    normalize_finish_reason,
    normalize_messages,
    validate_adapter,
)


class TestUtils:
    """Test utility functions."""

    def test_normalize_finish_reason(self) -> None:
        """Test finish reason normalization."""
        assert normalize_finish_reason(None) is None
        assert normalize_finish_reason("stop") == "stop"
        assert normalize_finish_reason("stop_sequence") == "stop"
        assert normalize_finish_reason("length") == "length"
        assert normalize_finish_reason("function_calls") == "function_calls"
        assert normalize_finish_reason("content_filter") == "content_filter"
        assert normalize_finish_reason("unknown_reason") == "unknown"

    def test_normalize_messages(self) -> None:
        """Test message normalization."""
        messages = [
            SystemMessage(content="You are helpful", source="system"),
            UserMessage(content="Hello", source="user"),
            AssistantMessage(content="Hi there", source="assistant"),
            FunctionExecutionResultMessage(content="Result", source="function"),
            {"role": "user", "content": "Already normalized"},
        ]

        normalized = normalize_messages(messages)

        assert len(normalized) == 5
        assert normalized[0] == {"role": "system", "content": "You are helpful"}
        assert normalized[1] == {"role": "user", "content": "Hello"}
        assert normalized[2] == {"role": "assistant", "content": "Hi there"}
        assert normalized[3] == {"role": "function", "content": "Result"}
        assert normalized[4] == {"role": "user", "content": "Already normalized"}

    def test_normalize_messages_fallback(self) -> None:
        """Test message normalization with unknown type."""

        class CustomMessage:
            def __init__(self, content: str):
                self.content = content

        messages = [CustomMessage("Custom content")]
        normalized = normalize_messages(messages)

        assert len(normalized) == 1
        assert normalized[0] == {"role": "user", "content": "Custom content"}

    def test_estimate_token_count(self) -> None:
        """Test token count estimation."""
        messages = [
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there how are you"},
        ]

        count = estimate_token_count(messages)
        assert count == 7  # "Hello world Hi there how are you" = 7 words

    def test_estimate_token_count_empty(self) -> None:
        """Test token count with empty messages."""
        messages = [
            {"role": "user", "content": ""},
            {"role": "assistant"},  # No content key
        ]

        count = estimate_token_count(messages)
        assert count == 1  # Minimum of 1

    def test_extract_content_success(self) -> None:
        """Test successful content extraction."""
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.choices[0].message.content = "Test content"

        content = extract_content(response)
        assert content == "Test content"

    def test_extract_content_none(self) -> None:
        """Test content extraction with None content."""
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.choices[0].message.content = None

        content = extract_content(response)
        assert content == ""

    def test_extract_content_no_choices(self) -> None:
        """Test content extraction with no choices."""
        response = Mock()
        response.choices = []

        content = extract_content(response)
        assert content == ""

    def test_extract_content_no_message(self) -> None:
        """Test content extraction with no message."""
        response = Mock()
        response.choices = [Mock()]
        del response.choices[0].message

        content = extract_content(response)
        assert content == ""

    def test_extract_usage_success(self) -> None:
        """Test successful usage extraction."""
        response = Mock()
        response.usage = Mock()
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 5

        usage = extract_usage(response)
        assert isinstance(usage, RequestUsage)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 5

    def test_extract_usage_no_usage(self) -> None:
        """Test usage extraction with no usage."""
        response = Mock()
        del response.usage

        usage = extract_usage(response)
        assert isinstance(usage, RequestUsage)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_extract_usage_missing_fields(self) -> None:
        """Test usage extraction with missing fields."""
        response = Mock()
        response.usage = Mock()
        # Missing prompt_tokens and completion_tokens

        usage = extract_usage(response)
        assert isinstance(usage, RequestUsage)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_extract_finish_reason_success(self) -> None:
        """Test successful finish reason extraction."""
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].finish_reason = "stop"

        reason = extract_finish_reason(response)
        assert reason == "stop"

    def test_extract_finish_reason_normalized(self) -> None:
        """Test finish reason extraction with normalization."""
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].finish_reason = "stop_sequence"

        reason = extract_finish_reason(response)
        assert reason == "stop"

    def test_extract_finish_reason_no_choices(self) -> None:
        """Test finish reason extraction with no choices."""
        response = Mock()
        response.choices = []

        reason = extract_finish_reason(response)
        assert reason is None

    def test_validate_adapter_success(self) -> None:
        """Test successful adapter validation."""
        adapter = Mock()
        adapter.completion = Mock()

        assert validate_adapter(adapter) is True

    def test_validate_adapter_none(self) -> None:
        """Test adapter validation with None."""
        with pytest.raises(ValueError, match="Adapter cannot be None"):
            validate_adapter(None)

    def test_validate_adapter_no_completion(self) -> None:
        """Test adapter validation without completion method."""
        adapter = Mock()
        del adapter.completion

        with pytest.raises(ValueError, match="Adapter must have a 'completion' method"):
            validate_adapter(adapter)

    def test_validate_adapter_completion_not_callable(self) -> None:
        """Test adapter validation with non-callable completion."""
        adapter = Mock()
        adapter.completion = "not callable"

        with pytest.raises(ValueError, match="Adapter 'completion' must be callable"):
            validate_adapter(adapter)
