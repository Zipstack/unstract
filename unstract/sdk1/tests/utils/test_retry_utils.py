"""Unit tests for retry_utils module."""

import errno
from unittest.mock import Mock

import pytest
from requests.exceptions import ConnectionError, HTTPError, Timeout
from unstract.sdk1.utils.retry_utils import (
    calculate_delay,
    create_retry_decorator,
    is_retryable_error,
    retry_platform_service_call,
    retry_prompt_service_call,
    retry_with_exponential_backoff,
)


class TestIsRetryableError:
    """Tests for is_retryable_error function."""

    def test_connection_error_is_retryable(self):
        """ConnectionError should be retryable."""
        error = ConnectionError("Connection failed")
        assert is_retryable_error(error) is True

    def test_timeout_is_retryable(self):
        """Timeout error should be retryable."""
        error = Timeout("Request timed out")
        assert is_retryable_error(error) is True

    @pytest.mark.parametrize("status_code", [502, 503, 504])
    def test_http_error_retryable_status_codes(self, status_code):
        """HTTPError with 502, 503, 504 should be retryable."""
        response = Mock()
        response.status_code = status_code
        error = HTTPError()
        error.response = response
        assert is_retryable_error(error) is True

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 500])
    def test_http_error_non_retryable_status_codes(self, status_code):
        """HTTPError with other status codes should not be retryable."""
        response = Mock()
        response.status_code = status_code
        error = HTTPError()
        error.response = response
        assert is_retryable_error(error) is False

    def test_http_error_without_response(self):
        """HTTPError without response should not be retryable."""
        error = HTTPError()
        error.response = None
        assert is_retryable_error(error) is False

    @pytest.mark.parametrize(
        "errno_code",
        [
            errno.ECONNREFUSED,
            getattr(errno, "ECONNRESET", 104),
            getattr(errno, "ETIMEDOUT", 110),
            getattr(errno, "EHOSTUNREACH", 113),
            getattr(errno, "ENETUNREACH", 101),
        ],
    )
    def test_os_error_retryable_errno(self, errno_code):
        """OSError with specific errno codes should be retryable."""
        error = OSError()
        error.errno = errno_code
        assert is_retryable_error(error) is True

    def test_os_error_non_retryable_errno(self):
        """OSError with other errno codes should not be retryable."""
        error = OSError()
        error.errno = errno.ENOENT  # File not found
        assert is_retryable_error(error) is False

    def test_other_exception_not_retryable(self):
        """Other exceptions should not be retryable."""
        error = ValueError("Invalid value")
        assert is_retryable_error(error) is False


class TestCalculateDelay:
    """Tests for calculate_delay function."""

    def test_exponential_backoff_without_jitter(self):
        """Test exponential backoff calculation without jitter."""
        base_delay = 1.0
        multiplier = 2.0
        max_delay = 60.0

        # Attempt 0: 1.0 * (2.0^0) = 1.0
        assert calculate_delay(
            0, base_delay, multiplier, max_delay, jitter=False
        ) == pytest.approx(1.0)

        # Attempt 1: 1.0 * (2.0^1) = 2.0
        assert calculate_delay(
            1, base_delay, multiplier, max_delay, jitter=False
        ) == pytest.approx(2.0)

        # Attempt 2: 1.0 * (2.0^2) = 4.0
        assert calculate_delay(
            2, base_delay, multiplier, max_delay, jitter=False
        ) == pytest.approx(4.0)

        # Attempt 3: 1.0 * (2.0^3) = 8.0
        assert calculate_delay(
            3, base_delay, multiplier, max_delay, jitter=False
        ) == pytest.approx(8.0)

    def test_exponential_backoff_with_jitter(self):
        """Test exponential backoff calculation with jitter."""
        base_delay = 1.0
        multiplier = 2.0
        max_delay = 60.0

        # With jitter, delay should be in range [base, base * 1.25]
        for attempt in range(4):
            base = base_delay * (multiplier**attempt)
            delay = calculate_delay(
                attempt, base_delay, multiplier, max_delay, jitter=True
            )
            assert base <= delay <= base * 1.25

    def test_max_delay_cap(self):
        """Test that max_delay caps the calculated delay."""
        base_delay = 1.0
        multiplier = 2.0
        max_delay = 5.0

        # Attempt 10: 1.0 * (2.0^10) = 1024.0, but capped at 5.0
        delay = calculate_delay(10, base_delay, multiplier, max_delay, jitter=False)
        assert delay == pytest.approx(5.0)

    def test_max_delay_cap_with_jitter(self):
        """Test that max_delay caps the delay even with jitter."""
        base_delay = 1.0
        multiplier = 2.0
        max_delay = 5.0

        # Even with jitter, should not exceed max_delay
        delay = calculate_delay(10, base_delay, multiplier, max_delay, jitter=True)
        assert delay <= max_delay


class TestRetryWithExponentialBackoff:
    """Tests for retry_with_exponential_backoff decorator."""

    def test_successful_call_first_attempt(self, mock_logger):
        """Test successful call on first attempt."""
        mock_func = Mock(return_value="success")

        decorator = retry_with_exponential_backoff(
            max_retries=3,
            max_time=60.0,
            base_delay=1.0,
            multiplier=2.0,
            jitter=False,
            exceptions=(Exception,),
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 1
        # Should not log retry success message for first attempt
        mock_logger.info.assert_not_called()

    def test_retry_after_transient_failure(self, mock_logger):
        """Test retry after transient failure."""
        mock_func = Mock(
            side_effect=[ConnectionError("Failed"), "success"], __name__="test_func"
        )

        decorator = retry_with_exponential_backoff(
            max_retries=3,
            max_time=60.0,
            base_delay=0.1,  # Short delay for testing
            multiplier=2.0,
            jitter=False,
            exceptions=(ConnectionError,),
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 2
        # Should log success after retry
        mock_logger.info.assert_called_once()
        assert "Successfully completed" in str(mock_logger.info.call_args)

    def test_max_retries_exceeded(self, mock_logger):
        """Test that max retries causes failure."""
        mock_func = Mock(
            side_effect=ConnectionError("Always fails"), __name__="test_func"
        )

        decorator = retry_with_exponential_backoff(
            max_retries=2,
            max_time=60.0,
            base_delay=0.1,
            multiplier=2.0,
            jitter=False,
            exceptions=(ConnectionError,),
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        with pytest.raises(ConnectionError, match="Always fails"):
            decorated_func()

        # Should attempt 3 times (initial + 2 retries)
        assert mock_func.call_count == 3
        # Should log giving up
        mock_logger.exception.assert_called()

    def test_max_time_exceeded(self, mock_logger):
        """Test that max time causes failure."""
        mock_func = Mock(
            side_effect=ConnectionError("Always fails"), __name__="test_func"
        )

        decorator = retry_with_exponential_backoff(
            max_retries=10,
            max_time=0.5,  # Very short max time
            base_delay=0.2,
            multiplier=2.0,
            jitter=False,
            exceptions=(ConnectionError,),
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        with pytest.raises(ConnectionError):
            decorated_func()

        # Should fail before reaching max retries due to time limit
        assert mock_func.call_count < 10

    def test_retry_with_custom_predicate(self, mock_logger):
        """Test retry with custom predicate."""

        def custom_predicate(e):
            # Only retry if message contains "retry"
            return "retry" in str(e)

        mock_func = Mock(
            side_effect=[Exception("retry please"), "success"], __name__="test_func"
        )

        decorator = retry_with_exponential_backoff(
            max_retries=3,
            max_time=60.0,
            base_delay=0.1,
            multiplier=2.0,
            jitter=False,
            exceptions=(Exception,),
            logger_instance=mock_logger,
            prefix="TEST",
            retry_predicate=custom_predicate,
        )
        decorated_func = decorator(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_no_retry_with_predicate_false(self, mock_logger):
        """Test no retry when predicate returns False."""

        def custom_predicate(e):
            return False

        mock_func = Mock(__name__="test_func", side_effect=Exception("Error"))

        decorator = retry_with_exponential_backoff(
            max_retries=3,
            max_time=60.0,
            base_delay=0.1,
            multiplier=2.0,
            jitter=False,
            exceptions=(Exception,),
            logger_instance=mock_logger,
            prefix="TEST",
            retry_predicate=custom_predicate,
        )
        decorated_func = decorator(mock_func)

        with pytest.raises(Exception, match="Error"):
            decorated_func()

        # Should not retry
        assert mock_func.call_count == 1

    def test_exception_not_in_tuple_not_retried(self, mock_logger):
        """Test that exceptions not in the tuple are not retried."""
        mock_func = Mock(__name__="test_func", side_effect=ValueError("Not retryable"))

        decorator = retry_with_exponential_backoff(
            max_retries=3,
            max_time=60.0,
            base_delay=0.1,
            multiplier=2.0,
            jitter=False,
            exceptions=(ConnectionError,),  # Only ConnectionError
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        with pytest.raises(ValueError, match="Not retryable"):
            decorated_func()

        # Should not retry
        assert mock_func.call_count == 1

    def test_delay_would_exceed_max_time(self, mock_logger):
        """Test that delay exceeding max time causes immediate failure."""
        mock_func = Mock(
            __name__="test_func", side_effect=ConnectionError("Always fails")
        )

        decorator = retry_with_exponential_backoff(
            max_retries=10,
            max_time=0.3,  # Very short max time
            base_delay=1.0,  # Large delay
            multiplier=2.0,
            jitter=False,
            exceptions=(ConnectionError,),
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        with pytest.raises(ConnectionError):
            decorated_func()

        # Should fail quickly due to delay exceeding remaining time
        mock_logger.exception.assert_called()
        exception_calls = [str(c) for c in mock_logger.exception.call_args_list]
        assert any("would exceed max time" in c for c in exception_calls)


class TestCreateRetryDecorator:
    """Tests for create_retry_decorator function."""

    def test_default_configuration(self, clean_env, mock_logger):
        """Test decorator with default configuration."""
        decorator = create_retry_decorator("TEST_SERVICE", logger_instance=mock_logger)

        mock_func = Mock(return_value="success")
        decorated_func = decorator(mock_func)

        result = decorated_func()

        assert result == "success"

    def test_environment_variable_configuration(self, clean_env, set_env, mock_logger):
        """Test decorator reads configuration from environment."""
        set_env(
            "TEST_SERVICE",
            max_retries=5,
            max_time=120,
            base_delay=2.0,
            multiplier=3.0,
            jitter="false",
        )

        mock_func = Mock(
            __name__="test_func", side_effect=[ConnectionError("Failed"), "success"]
        )

        decorator = create_retry_decorator("TEST_SERVICE", logger_instance=mock_logger)
        decorated_func = decorator(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_invalid_max_retries(self, clean_env, set_env):
        """Test that negative max_retries raises error."""
        set_env("TEST_SERVICE", max_retries=-1)

        with pytest.raises(ValueError, match="MAX_RETRIES must be >= 0"):
            create_retry_decorator("TEST_SERVICE")

    def test_invalid_max_time(self, clean_env, set_env):
        """Test that non-positive max_time raises error."""
        set_env("TEST_SERVICE", max_time=0)

        with pytest.raises(ValueError, match="MAX_TIME must be > 0"):
            create_retry_decorator("TEST_SERVICE")

    def test_invalid_base_delay(self, clean_env, set_env):
        """Test that non-positive base_delay raises error."""
        set_env("TEST_SERVICE", base_delay=-0.5)

        with pytest.raises(ValueError, match="BASE_DELAY must be > 0"):
            create_retry_decorator("TEST_SERVICE")

    def test_invalid_multiplier(self, clean_env, set_env):
        """Test that non-positive multiplier raises error."""
        set_env("TEST_SERVICE", multiplier=0)

        with pytest.raises(ValueError, match="MULTIPLIER must be > 0"):
            create_retry_decorator("TEST_SERVICE")

    @pytest.mark.parametrize("jitter_value", ["true", "false"])
    def test_jitter_values(self, jitter_value, clean_env, set_env, mock_logger):
        """Test jitter configuration values."""
        set_env("TEST_SERVICE", jitter=jitter_value)

        decorator = create_retry_decorator("TEST_SERVICE", logger_instance=mock_logger)

        # Should not raise error
        assert decorator is not None

    def test_custom_exceptions_only(self, clean_env, mock_logger):
        """Test decorator with custom exceptions and no predicate."""
        decorator = create_retry_decorator(
            "TEST_SERVICE",
            exceptions=(ValueError, TypeError),
            logger_instance=mock_logger,
        )

        mock_func = Mock(
            __name__="test_func", side_effect=[ValueError("Error"), "success"]
        )
        decorated_func = decorator(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_custom_predicate_only(self, clean_env, mock_logger):
        """Test decorator with custom predicate and no exceptions."""

        def custom_predicate(e):
            return isinstance(e, ValueError)

        decorator = create_retry_decorator(
            "TEST_SERVICE",
            retry_predicate=custom_predicate,
            logger_instance=mock_logger,
        )

        mock_func = Mock(
            __name__="test_func", side_effect=[ValueError("Error"), "success"]
        )
        decorated_func = decorator(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_both_exceptions_and_predicate(self, clean_env, mock_logger):
        """Test decorator with both exceptions and predicate."""

        def custom_predicate(e):
            return "retry" in str(e)

        decorator = create_retry_decorator(
            "TEST_SERVICE",
            exceptions=(ValueError,),
            retry_predicate=custom_predicate,
            logger_instance=mock_logger,
        )

        # Should retry - ValueError with "retry" in message
        mock_func = Mock(
            __name__="test_func", side_effect=[ValueError("retry please"), "success"]
        )
        decorated_func = decorator(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_exceptions_match_but_predicate_false(self, clean_env, mock_logger):
        """Test that predicate can prevent retry even if exception matches."""

        def custom_predicate(e):
            return "retry" in str(e)

        decorator = create_retry_decorator(
            "TEST_SERVICE",
            exceptions=(ValueError,),
            retry_predicate=custom_predicate,
            logger_instance=mock_logger,
        )

        # ValueError matches but predicate returns False (no "retry" substring)
        mock_func = Mock(
            __name__="test_func", side_effect=ValueError("do not attempt again")
        )
        decorated_func = decorator(mock_func)

        with pytest.raises(ValueError, match="do not attempt again"):
            decorated_func()

        # Should not retry
        assert mock_func.call_count == 1


class TestPreconfiguredDecorators:
    """Tests for pre-configured decorators."""

    def test_retry_platform_service_call_exists(self):
        """Test that retry_platform_service_call decorator exists."""
        assert retry_platform_service_call is not None

    def test_retry_prompt_service_call_exists(self):
        """Test that retry_prompt_service_call decorator exists."""
        assert retry_prompt_service_call is not None

    def test_platform_service_decorator_retries_on_connection_error(self, clean_env):
        """Test platform service decorator retries ConnectionError."""
        mock_func = Mock(
            __name__="test_func", side_effect=[ConnectionError("Failed"), "success"]
        )

        decorated_func = retry_platform_service_call(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 2

    def test_prompt_service_decorator_retries_on_timeout(self, clean_env):
        """Test prompt service decorator retries Timeout."""
        mock_func = Mock(
            __name__="test_func", side_effect=[Timeout("Timed out"), "success"]
        )

        decorated_func = retry_prompt_service_call(mock_func)

        result = decorated_func()

        assert result == "success"
        assert mock_func.call_count == 2


class TestRetryLogging:
    """Tests for retry logging behavior."""

    def test_warning_logged_on_retry(self, mock_logger):
        """Test that warning is logged on retry attempt."""
        mock_func = Mock(
            __name__="test_func", side_effect=[ConnectionError("Failed"), "success"]
        )

        decorator = retry_with_exponential_backoff(
            max_retries=3,
            max_time=60.0,
            base_delay=0.1,
            multiplier=2.0,
            jitter=False,
            exceptions=(ConnectionError,),
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        decorated_func()

        # Should log warning about retry
        mock_logger.warning.assert_called_once()
        warning_msg = str(mock_logger.warning.call_args)
        assert "Retry" in warning_msg
        assert "TEST" in warning_msg

    def test_info_logged_on_success_after_retry(self, mock_logger):
        """Test that info is logged when successful after retry."""
        mock_func = Mock(
            __name__="test_func", side_effect=[ConnectionError("Failed"), "success"]
        )

        decorator = retry_with_exponential_backoff(
            max_retries=3,
            max_time=60.0,
            base_delay=0.1,
            multiplier=2.0,
            jitter=False,
            exceptions=(ConnectionError,),
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        decorated_func()

        # Should log success after retry
        mock_logger.info.assert_called_once()
        info_msg = str(mock_logger.info.call_args)
        assert "Successfully completed" in info_msg

    def test_exception_logged_on_giving_up(self, mock_logger):
        """Test that exception is logged when giving up."""
        mock_func = Mock(
            __name__="test_func", side_effect=ConnectionError("Always fails")
        )

        decorator = retry_with_exponential_backoff(
            max_retries=1,
            max_time=60.0,
            base_delay=0.1,
            multiplier=2.0,
            jitter=False,
            exceptions=(ConnectionError,),
            logger_instance=mock_logger,
            prefix="TEST",
        )
        decorated_func = decorator(mock_func)

        with pytest.raises(ConnectionError):
            decorated_func()

        # Should log exception when giving up
        mock_logger.exception.assert_called()
        exception_msg = str(mock_logger.exception.call_args)
        assert "Giving up" in exception_msg or "exceeded" in exception_msg
