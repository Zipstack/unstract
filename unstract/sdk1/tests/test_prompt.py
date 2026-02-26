"""Integration tests for prompt module with retry logic."""

from typing import Any, Self
from unittest.mock import MagicMock, Mock, patch

import pytest
from pytest import MonkeyPatch
from requests.exceptions import ConnectionError, Timeout

from unstract.sdk1.prompt import PromptTool


class TestPromptToolRetry:
    """Tests for PromptTool retry functionality."""

    @pytest.fixture
    def mock_tool(self: Self) -> MagicMock:
        """Create a mock tool for testing."""
        tool = MagicMock()
        tool.get_env_or_die.side_effect = lambda key: {
            "PLATFORM_API_KEY": "test-api-key",
        }.get(key, "mock-value")
        tool.stream_log = MagicMock()
        tool.stream_error_and_exit = MagicMock()
        return tool

    @pytest.fixture
    def prompt_tool(self: Self, mock_tool: MagicMock) -> PromptTool:
        """Create a PromptTool instance."""
        return PromptTool(
            tool=mock_tool,
            prompt_host="http://localhost",
            prompt_port="3003",
            is_public_call=False,
            request_id="test-request-id",
        )

    def test_success_on_first_attempt(
        self: Self, prompt_tool: PromptTool, clean_env: MonkeyPatch
    ) -> None:
        """Test successful service call on first attempt."""
        expected_response = {"result": "success"}
        payload = {"prompt": "test"}

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = expected_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            result = prompt_tool._call_service("answer-prompt", payload=payload)

            assert result == expected_response
            assert mock_post.call_count == 1

    @pytest.mark.parametrize(
        "error_type,error_instance",
        [
            ("ConnectionError", ConnectionError("Connection failed")),
            ("Timeout", Timeout("Request timed out")),
        ],
    )
    def test_retry_on_errors(
        self: Self,
        prompt_tool: PromptTool,
        error_type: str,
        error_instance: Exception,
        clean_env: MonkeyPatch,
    ) -> None:
        """Test service retries on ConnectionError and Timeout."""
        expected_response = {"result": "success"}
        payload = {"prompt": "test"}

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = expected_response
            mock_response.raise_for_status = Mock()

            mock_post.side_effect = [
                error_instance,
                mock_response,
            ]

            result = prompt_tool._call_service("answer-prompt", payload=payload)

            assert result == expected_response
            assert mock_post.call_count == 2

    @pytest.mark.slow
    def test_max_retries_exceeded(
        self: Self, mock_tool: MagicMock, clean_env: MonkeyPatch
    ) -> None:
        """Test service call fails after exceeding max retries."""
        prompt_tool = PromptTool(
            tool=mock_tool,
            prompt_host="http://localhost",
            prompt_port="3003",
            is_public_call=False,
            request_id="test-request-id",
        )

        payload = {"prompt": "test"}

        with patch("requests.post") as mock_post:
            mock_post.side_effect = ConnectionError("Persistent failure")

            # Exception handled by decorator
            with pytest.raises(ConnectionError):
                prompt_tool._call_service("answer-prompt", payload=payload)

            # Default: 3 retries + 1 initial = 4 attempts
            assert mock_post.call_count == 4

    @pytest.mark.parametrize(
        "method_name,payload",
        [
            ("answer_prompt", {"prompts": ["test"]}),
            ("index", {"document": "test"}),
            ("extract", {"doc_id": "123"}),
            ("summarize", {"text": "test"}),
        ],
    )
    def test_wrapper_methods_retry(
        self: Self,
        prompt_tool: PromptTool,
        method_name: str,
        payload: dict[str, Any],
        clean_env: MonkeyPatch,
    ) -> None:
        """Test that wrapper methods inherit retry behavior."""
        expected_response = {
            "answers": ["result"],
            "doc_id": "doc-123",
            "extracted_text": "text",
            "summary": "summary",
        }

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = expected_response
            mock_response.raise_for_status = Mock()

            mock_post.side_effect = [
                ConnectionError("Transient failure"),
                mock_response,
            ]

            getattr(prompt_tool, method_name)(payload)

            assert mock_post.call_count == 2

    @pytest.mark.slow
    def test_error_handling_with_retry(
        self: Self, mock_tool: MagicMock, clean_env: MonkeyPatch
    ) -> None:
        """Test error handling decorator works with retry."""
        prompt_tool = PromptTool(
            tool=mock_tool,
            prompt_host="http://localhost",
            prompt_port="3003",
            is_public_call=False,
            request_id="test-request-id",
        )

        payload = {"prompt": "test"}

        with patch("requests.post") as mock_post:
            mock_post.side_effect = ConnectionError("Persistent failure")

            # Error handler should catch after all retries
            result = prompt_tool.answer_prompt(payload)

            # handle_service_exceptions decorator calls stream_error_and_exit
            assert result is None
            prompt_tool.tool.stream_error_and_exit.assert_called()
