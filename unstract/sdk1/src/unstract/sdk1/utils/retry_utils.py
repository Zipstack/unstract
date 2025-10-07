"""Generic retry utilities with custom exponential backoff implementation."""

import errno
import logging
import os
import random
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from requests.exceptions import ConnectionError, HTTPError, Timeout

logger = logging.getLogger(__name__)


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable.

    Handles:
    - ConnectionError and Timeout from requests
    - HTTPError with status codes 502, 503, 504
    - OSError with specific errno codes (ECONNREFUSED, ECONNRESET, etc.)

    Args:
        error: The exception to check

    Returns:
        True if the error should trigger a retry
    """
    # Requests connection and timeout errors
    if isinstance(error, ConnectionError | Timeout):
        return True

    # HTTP errors with specific status codes
    if isinstance(error, HTTPError):
        if hasattr(error, "response") and error.response is not None:
            status_code = error.response.status_code
            # Retry on server errors and bad gateway
            if status_code in [502, 503, 504]:
                return True

    # OS-level connection failures (preserving existing errno checks)
    if isinstance(error, OSError) and error.errno in {
        errno.ECONNREFUSED,  # Connection refused
        getattr(errno, "ECONNRESET", 104),  # Connection reset by peer
        getattr(errno, "ETIMEDOUT", 110),  # Connection timed out
        getattr(errno, "EHOSTUNREACH", 113),  # No route to host
        getattr(errno, "ENETUNREACH", 101),  # Network is unreachable
    }:
        return True

    return False


def calculate_delay(
    attempt: int,
    base_delay: float,
    multiplier: float,
    max_delay: float,
    jitter: bool = True,
) -> float:
    """Calculate delay for the next retry attempt with exponential backoff.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        multiplier: Backoff multiplier
        max_delay: Maximum delay in seconds
        jitter: Whether to add random jitter

    Returns:
        Delay in seconds before the next retry
    """
    # Calculate exponential backoff
    base = base_delay * (multiplier**attempt)

    # Add jitter if enabled (0-25% of base)
    if jitter:
        delay = base + (base * random.uniform(0, 0.25))
    else:
        delay = base

    # Enforce cap after jitter
    return min(delay, max_delay)


def retry_with_exponential_backoff(
    max_retries: int,
    max_time: float,
    base_delay: float,
    multiplier: float,
    jitter: bool,
    exceptions: tuple[type[Exception], ...],
    logger_instance: logging.Logger,
    prefix: str,
    retry_predicate: Callable[[Exception], bool] | None = None,
) -> Callable:
    """Create retry decorator with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        max_time: Maximum total time in seconds
        base_delay: Initial delay in seconds
        multiplier: Backoff multiplier
        jitter: Whether to add jitter
        exceptions: Exception types to catch for retries
        logger_instance: Logger instance for retry messages
        prefix: Service prefix for logging
        retry_predicate: Optional callable to determine if exception should trigger retry

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            last_exception = None

            for attempt in range(max_retries + 1):  # +1 for initial attempt
                try:
                    # Try to execute the function
                    result = func(*args, **kwargs)

                    # If successful and we had retried, log success
                    if attempt > 0:
                        logger_instance.info(
                            "Successfully completed '%s' after %d retry attempt(s)",
                            func.__name__,
                            attempt,
                        )

                    return result

                except exceptions as e:
                    last_exception = e

                    # Check if the error should trigger a retry
                    # First check if it's in the allowed exception types (already caught)
                    # Then check using the predicate if provided
                    should_retry = True
                    if retry_predicate is not None:
                        should_retry = retry_predicate(e)

                    # Check if we've exceeded max time
                    elapsed_time = time.time() - start_time
                    if elapsed_time >= max_time:
                        logger_instance.exception(
                            "Giving up '%s' after %.1fs (max time exceeded): %s",
                            func.__name__,
                            elapsed_time,
                            e,
                        )
                        raise

                    # If not retryable or last attempt, raise the error
                    if not should_retry or attempt == max_retries:
                        if attempt > 0:
                            logger_instance.exception(
                                "Giving up '%s' after %d attempt(s) for %s",
                                func.__name__,
                                attempt + 1,
                                prefix,
                            )
                        raise

                    # Calculate delay for next retry
                    delay = calculate_delay(
                        attempt, base_delay, multiplier, max_time, jitter
                    )

                    # Ensure we don't exceed max_time with the delay
                    remaining_time = max_time - elapsed_time
                    if delay >= remaining_time:
                        logger_instance.exception(
                            "Giving up '%s' - next delay %.1fs would exceed "
                            "max time %.1fs",
                            func.__name__,
                            delay,
                            max_time,
                        )
                        raise

                    # Log retry attempt
                    logger_instance.warning(
                        "Retry %d/%d for %s: %s (waiting %.1fs)",
                        attempt + 1,
                        max_retries,
                        prefix,
                        e,
                        delay,
                    )

                    # Wait before retrying
                    time.sleep(delay)

                except Exception as e:
                    # Exception not in the exceptions tuple - don't retry
                    last_exception = e
                    raise

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def create_retry_decorator(
    prefix: str,
    exceptions: tuple[type[Exception], ...] | None = None,
    retry_predicate: Callable[[Exception], bool] | None = None,
    logger_instance: logging.Logger | None = None,
) -> Callable:
    """Create a configured retry decorator for a specific service.

    Args:
        prefix: Environment variable prefix for configuration
        exceptions: Tuple of exception types to retry on.
                   Defaults to (ConnectionError, HTTPError, Timeout, OSError)
        retry_predicate: Optional callable to determine if exception should trigger retry.
                        If only exceptions list provided, retry on those exceptions.
                        If only predicate provided, use predicate (catch all exceptions).
                        If both provided, first filter by exceptions then check predicate.
        logger_instance: Optional logger for retry events

    Environment variables (using prefix):
        {prefix}_MAX_RETRIES: Maximum retry attempts (default: 3)
        {prefix}_MAX_TIME: Maximum total time in seconds (default: 60)
        {prefix}_BASE_DELAY: Initial delay in seconds (default: 1.0)
        {prefix}_MULTIPLIER: Backoff multiplier (default: 2.0)
        {prefix}_JITTER: Enable jitter true/false (default: true)

    Returns:
        Configured retry decorator
    """
    # Handle different combinations of exceptions and predicate
    if exceptions is None and retry_predicate is None:
        # Default case: use specific exceptions with is_retryable_error predicate
        exceptions = (ConnectionError, HTTPError, Timeout, OSError)
        retry_predicate = is_retryable_error
    elif exceptions is None and retry_predicate is not None:
        # Only predicate provided: catch all exceptions and use predicate
        exceptions = (Exception,)
    elif exceptions is not None and retry_predicate is None:
        # Only exceptions provided: retry on those exceptions
        pass  # exceptions already set, no predicate needed
    # Both provided: use both (exceptions filter first, then predicate)

    # Load configuration from environment
    max_retries = int(os.getenv(f"{prefix}_MAX_RETRIES", "3"))
    max_time = float(os.getenv(f"{prefix}_MAX_TIME", "60"))
    base_delay = float(os.getenv(f"{prefix}_BASE_DELAY", "1.0"))
    multiplier = float(os.getenv(f"{prefix}_MULTIPLIER", "2.0"))
    use_jitter = os.getenv(f"{prefix}_JITTER", "true").strip().lower() in {
        "true",
        "1",
        "yes",
        "on",
    }

    if max_retries < 0:
        raise ValueError(f"{prefix}_MAX_RETRIES must be >= 0")
    if max_time <= 0:
        raise ValueError(f"{prefix}_MAX_TIME must be > 0")
    if base_delay <= 0:
        raise ValueError(f"{prefix}_BASE_DELAY must be > 0")
    if multiplier <= 0:
        raise ValueError(f"{prefix}_MULTIPLIER must be > 0")

    if logger_instance is None:
        logger_instance = logger

    return retry_with_exponential_backoff(
        max_retries=max_retries,
        max_time=max_time,
        base_delay=base_delay,
        multiplier=multiplier,
        jitter=use_jitter,
        exceptions=exceptions,
        logger_instance=logger_instance,
        prefix=prefix,
        retry_predicate=retry_predicate,
    )


# Retry configured through below envs.
# - PLATFORM_SERVICE_MAX_RETRIES (default: 3)
# - PLATFORM_SERVICE_MAX_TIME (default: 60s)
# - PLATFORM_SERVICE_BASE_DELAY (default: 1.0s)
# - PLATFORM_SERVICE_MULTIPLIER (default: 2.0)
# - PLATFORM_SERVICE_JITTER (default: true)
retry_platform_service_call = create_retry_decorator("PLATFORM_SERVICE")

# Retry configured through below envs.
# - PROMPT_SERVICE_MAX_RETRIES (default: 3)
# - PROMPT_SERVICE_MAX_TIME (default: 60s)
# - PROMPT_SERVICE_BASE_DELAY (default: 1.0s)
# - PROMPT_SERVICE_MULTIPLIER (default: 2.0)
# - PROMPT_SERVICE_JITTER (default: true)
retry_prompt_service_call = create_retry_decorator("PROMPT_SERVICE")
