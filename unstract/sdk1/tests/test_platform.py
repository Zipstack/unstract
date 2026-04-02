"""Integration tests for platform module with retry logic."""

from unittest.mock import MagicMock, Mock, patch

import pytest
from _pytest.monkeypatch import MonkeyPatch
from requests.exceptions import ConnectionError, HTTPError
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.platform import PlatformHelper


class TestPlatformHelperRetry:
    """Tests for PlatformHelper retry functionality."""

    @pytest.fixture
    def mock_tool(self) -> MagicMock:
        """Create a mock tool for testing."""
        tool = MagicMock()
        tool.get_env_or_die.side_effect = lambda key: {
            "PLATFORM_HOST": "http://localhost",
            "PLATFORM_PORT": "3001",
            "PLATFORM_API_KEY": "test-api-key",
        }.get(key, "mock-value")
        tool.stream_log = MagicMock()
        tool.stream_error_and_exit = MagicMock()
        return tool

    @pytest.fixture
    def platform_helper(self, mock_tool: MagicMock) -> PlatformHelper:
        """Create a PlatformHelper instance."""
        return PlatformHelper(
            tool=mock_tool,
            platform_host="http://localhost",
            platform_port="3001",
            request_id="test-request-id",
        )

    @pytest.mark.parametrize(
        "method_name,method_args,http_method",
        [
            ("_get_adapter_configuration", ("test-adapter-id",), "GET"),
            ("_call_service", ("test-endpoint",), "GET"),
        ],
    )
    def test_success_on_first_attempt(
        self,
        mock_tool: MagicMock,
        platform_helper: PlatformHelper,
        method_name: str,
        method_args: tuple[str, ...],
        http_method: str,
        clean_env: MonkeyPatch,
    ) -> None:
        """Test successful calls on first attempt for various methods."""
        expected_data = {"adapter_id": "test", "config": {}}

        patch_target = f"requests.{http_method.lower()}"
        with patch(patch_target) as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = expected_data
            mock_response.raise_for_status = Mock()
            mock_request.return_value = mock_response

            if method_name == "_get_adapter_configuration":
                PlatformHelper._get_adapter_configuration(mock_tool, *method_args)
            else:
                getattr(platform_helper, method_name)(*method_args)

            assert mock_request.call_count == 1

    @pytest.mark.parametrize(
        "method_name,method_args",
        [
            ("_get_adapter_configuration", ("test-adapter-id",)),
            ("_call_service", ("test-endpoint",)),
        ],
    )
    def test_retry_on_connection_error(
        self,
        mock_tool: MagicMock,
        platform_helper: PlatformHelper,
        method_name: str,
        method_args: tuple[str, ...],
        clean_env: MonkeyPatch,
    ) -> None:
        """Test methods retry on ConnectionError."""
        expected_data = {"result": "success"}

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = expected_data
            mock_response.raise_for_status = Mock()

            mock_get.side_effect = [
                ConnectionError("Transient failure"),
                mock_response,
            ]

            if method_name == "_get_adapter_configuration":
                PlatformHelper._get_adapter_configuration(mock_tool, *method_args)
            else:
                getattr(platform_helper, method_name)(*method_args)

            assert mock_get.call_count == 2

    @pytest.mark.slow
    def test_max_retries_exceeded(
        self, mock_tool: MagicMock, clean_env: MonkeyPatch
    ) -> None:
        """Test service call fails after exceeding max retries."""
        platform_helper = PlatformHelper(
            tool=mock_tool,
            platform_host="http://localhost",
            platform_port="3001",
        )

        with patch("requests.get") as mock_get:
            mock_get.side_effect = ConnectionError("Persistent failure")

            with pytest.raises(ConnectionError):
                platform_helper._call_service("test-endpoint")

            # Default: 3 retries + 1 initial = 4 attempts
            assert mock_get.call_count == 4

    def test_non_retryable_http_error(
        self, mock_tool: MagicMock, clean_env: MonkeyPatch
    ) -> None:
        """Test non-retryable HTTP errors (404, 400) don't trigger retry."""
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"error": "Not found"}

            http_error = HTTPError()
            http_error.response = mock_response
            mock_get.side_effect = http_error

            with pytest.raises(SdkError, match="Error retrieving adapter"):
                PlatformHelper._get_adapter_configuration(mock_tool, "test-adapter-id")

            # Should not retry 404
            assert mock_get.call_count == 1

    @pytest.mark.parametrize("status_code", [502, 503, 504])
    def test_retryable_http_errors(
        self, mock_tool: MagicMock, status_code: int, clean_env: MonkeyPatch
    ) -> None:
        """Test retryable HTTP errors (502, 503, 504) trigger retry."""
        expected_data = {"adapter_id": "test", "config": {}}

        with patch("requests.get") as mock_get:
            # First attempt: retryable HTTP error
            http_error = HTTPError()
            error_response = Mock()
            error_response.status_code = status_code
            error_response.json.return_value = {"error": "Service unavailable"}
            http_error.response = error_response

            # Second attempt: success
            success_response = Mock()
            success_response.json.return_value = expected_data
            success_response.raise_for_status = Mock()

            mock_get.side_effect = [http_error, success_response]

            result = PlatformHelper._get_adapter_configuration(
                mock_tool, "test-adapter-id"
            )

            # Should retry and succeed
            assert mock_get.call_count == 2
            assert result == expected_data

    @pytest.mark.slow
    def test_connection_error_converted_to_sdk_error(
        self, mock_tool: MagicMock, clean_env: MonkeyPatch
    ) -> None:
        """Test get_adapter_config wraps ConnectionError as SdkError."""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = ConnectionError("Connection failed")

            with pytest.raises(SdkError, match="Unable to connect to platform service"):
                PlatformHelper.get_adapter_config(mock_tool, "test-adapter-id")

    def test_post_method_retry(
        self, platform_helper: PlatformHelper, clean_env: MonkeyPatch
    ) -> None:
        """Test POST requests also support retry."""
        payload = {"key": "value"}
        expected_response = {"status": "OK"}

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = expected_response
            mock_response.raise_for_status = Mock()

            mock_post.side_effect = [
                ConnectionError("Transient failure"),
                mock_response,
            ]

            result = platform_helper._call_service(
                "test-endpoint", payload=payload, method="POST"
            )

            assert result == expected_response
            assert mock_post.call_count == 2

    def test_retry_logging(self, mock_tool: MagicMock, clean_env: MonkeyPatch) -> None:
        """Test that retry attempts are logged."""
        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {}
            mock_response.raise_for_status = Mock()

            mock_get.side_effect = [
                ConnectionError("Transient failure"),
                mock_response,
            ]

            helper = PlatformHelper(
                tool=mock_tool,
                platform_host="http://localhost",
                platform_port="3001",
            )

            helper._call_service("test-endpoint")

            # Verify logging occurred
            mock_tool.stream_log.assert_called()
            log_calls = [str(c) for c in mock_tool.stream_log.call_args_list]
            assert any("retry" in call.lower() for call in log_calls)
