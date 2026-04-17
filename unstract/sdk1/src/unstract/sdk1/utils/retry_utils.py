"""Generic retry utilities with custom exponential backoff implementation."""

import asyncio
import builtins
import errno
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable, Generator, Iterable
from functools import wraps
from typing import Any

from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError, Timeout

logger = logging.getLogger(__name__)

# HTTP status codes that indicate transient server-side failures worth retrying.
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

# Exception class names (from litellm, openai, httpx) that indicate transient
# connection/timeout failures. Resolved via duck-typing to avoid importing
# litellm in this utility module.
_RETRYABLE_ERROR_NAMES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "Timeout",
        "ConnectTimeout",
        "ReadTimeout",
    }
)


def is_retryable_litellm_error(error: Exception) -> bool:
    """Check if a litellm/provider API error should trigger a retry.

    Distinct from is_retryable_error() which handles requests-library exceptions
    (requests.ConnectionError, requests.HTTPError.response.status_code, OSError).
    litellm/openai/httpx have a separate exception hierarchy: status_code lives
    on the exception itself, and class names like APIConnectionError don't inherit
    from the requests types. Uses duck-typing to avoid importing litellm directly.
    """
    # Python built-in connection / timeout base classes (not requests.ConnectionError)
    if isinstance(error, builtins.ConnectionError | builtins.TimeoutError):
        return True

    # litellm/openai/httpx exception types that don't inherit from the
    # built-ins above but still represent transient network failures.
    # Check MRO to also catch subclasses of these error types.
    if any(cls.__name__ in _RETRYABLE_ERROR_NAMES for cls in type(error).__mro__):
        return True

    # Status-code check covers litellm.RateLimitError (429),
    # InternalServerError (500), ServiceUnavailableError (503), etc.
    status_code = getattr(error, "status_code", None)
    if status_code is not None and status_code in RETRYABLE_STATUS_CODES:
        return True

    return False


# ── Shared retry decision ───────────────────────────────────────────────────


def _extract_retry_after(error: Exception) -> float | None:
    """Return the server-supplied Retry-After delay in seconds, if present.

    Honors the provider's explicit cool-down hint on 429/503 responses so our
    backoff doesn't hammer the provider before its requested wait. Only the
    integer/float seconds form is supported; RFC 7231 HTTP-date values fall
    back to exponential backoff.
    """
    response = getattr(error, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return None


def _get_retry_delay(
    error: Exception,
    attempt: int,
    max_retries: int,
    retry_predicate: Callable[[Exception], bool] | None,
    description: str,
    logger_instance: logging.Logger,
    base_delay: float = 1.0,
    multiplier: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float | None:
    """Decide whether to retry and compute the backoff delay.

    Returns delay in seconds if the error is retryable, None otherwise.
    The caller is responsible for sleeping (sync or async) and re-raising
    when None is returned.
    """
    should_retry = retry_predicate(error) if retry_predicate is not None else True

    logger_instance.debug(
        "Retry decision: attempt=%d/%d error=%s retryable=%s description=%s",
        attempt + 1,
        max_retries + 1,
        type(error).__name__,
        should_retry,
        description,
    )

    if not should_retry or attempt >= max_retries:
        # Shared exhaustion log — fires for every retry helper once retries
        # were actually attempted (attempt > 0) and the error was retryable
        # (i.e. we stopped because we ran out of attempts, not because the
        # error type was non-retryable).
        if attempt > 0 and should_retry:
            logger_instance.exception(
                "Giving up %s after %d attempt(s)",
                description,
                attempt + 1,
            )
        return None

    # Provider-supplied Retry-After (e.g. 429/503) wins over our exponential
    # backoff — matches the behavior the OpenAI/Azure SDKs give natively.
    retry_after = _extract_retry_after(error)
    if retry_after is not None:
        delay = retry_after
    else:
        delay = calculate_delay(attempt, base_delay, multiplier, max_delay, jitter)
    logger_instance.warning(
        "Retry %d/%d for %s: %s (waiting %.1fs)",
        attempt + 1,
        max_retries,
        description,
        error,
        delay,
    )
    return delay


# ── Generic retry wrappers ──────────────────────────────────────────────────
# Unlike the decorator-based retry_with_exponential_backoff (env-var configured,
# sync-only), these accept max_retries at call time and support async + generators.
# All delegate retry decisions to _get_retry_delay above.


def _validate_max_retries(max_retries: int) -> None:
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")


def pop_litellm_retry_kwargs(kwargs: dict[str, Any], context: str = "") -> int:
    """Pop max_retries from kwargs and disable litellm's built-in retries.

    litellm has two separate retry mechanisms:
    - max_retries: passed to the SDK client (OpenAI/Azure) as its
      constructor arg — triggers SDK-level retries.
    - num_retries: activates litellm's own completion_with_retries wrapper.

    Both are zeroed so the outer retry helpers (call_with_retry etc.) are
    the single source of truth. Note that num_retries=0 is dropped from
    embedding kwargs by litellm.drop_params=True, but setting it keeps the
    intent explicit and consistent across LLM/embedding paths.

    Returns the user-configured max_retries value (or 0 if unset).
    """
    max_retries = kwargs.pop("max_retries", None) or 0
    kwargs["max_retries"] = 0
    kwargs["num_retries"] = 0
    suffix = f" for {context}" if context else ""
    logger.debug(
        "Extracted max_retries=%d, disabled litellm retry "
        "(max_retries=0, num_retries=0)%s",
        max_retries,
        suffix,
    )
    return max_retries


def call_with_retry[T](
    fn: Callable[[], T],
    *,
    max_retries: int,
    retry_predicate: Callable[[Exception], bool],
    description: str = "",
    logger_instance: logging.Logger | None = None,
) -> T:
    """Execute fn() with retry on transient errors."""
    _validate_max_retries(max_retries)
    log = logger_instance or logger
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            delay = _get_retry_delay(
                e, attempt, max_retries, retry_predicate, description, log
            )
            if delay is None:
                raise
            time.sleep(delay)
    raise RuntimeError("unreachable")  # for type-checker: loop always returns or raises


async def acall_with_retry[T](
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    retry_predicate: Callable[[Exception], bool],
    description: str = "",
    logger_instance: logging.Logger | None = None,
) -> T:
    """Async version of call_with_retry — awaits fn()."""
    _validate_max_retries(max_retries)
    log = logger_instance or logger
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            delay = _get_retry_delay(
                e, attempt, max_retries, retry_predicate, description, log
            )
            if delay is None:
                raise
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")  # for type-checker: loop always returns or raises


def iter_with_retry[T](
    fn: Callable[[], Iterable[T]],
    *,
    max_retries: int,
    retry_predicate: Callable[[Exception], bool],
    description: str = "",
    logger_instance: logging.Logger | None = None,
) -> Generator[T, None, None]:
    """Yield from fn() with retry. Only retries before the first yield.

    Once items have been yielded to the caller a mid-iteration failure is
    raised immediately — partial output can't be un-yielded.
    """
    _validate_max_retries(max_retries)
    log = logger_instance or logger
    for attempt in range(max_retries + 1):
        has_yielded = False
        gen = fn()
        try:
            for item in gen:
                has_yielded = True
                yield item
            return
        except Exception as e:
            # Close generator to release in-flight HTTP/socket resources
            # before retrying — otherwise streaming providers leak sockets
            # until GC.
            close = getattr(gen, "close", None)
            if callable(close):
                close()
            if has_yielded:
                raise
            delay = _get_retry_delay(
                e, attempt, max_retries, retry_predicate, description, log
            )
            if delay is None:
                raise
            time.sleep(delay)


def is_retryable_error(error: Exception) -> bool:
    """Check if a requests-library HTTP error should trigger a retry.

    For retrying internal service calls (platform-service, prompt-service) that
    use the requests library. Distinct from is_retryable_litellm_error() which
    handles litellm/openai/httpx exceptions with different class hierarchies
    (e.g. error.status_code vs error.response.status_code).
    """
    # Requests connection and timeout errors
    if isinstance(error, RequestsConnectionError | Timeout):
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


def _invoke_with_retries(
    func: Callable,
    args: tuple,
    kwargs: dict,
    *,
    max_retries: int,
    base_delay: float,
    multiplier: float,
    jitter: bool,
    exceptions: tuple[type[Exception], ...],
    logger_instance: logging.Logger,
    prefix: str,
    retry_predicate: Callable[[Exception], bool] | None,
) -> Any:  # noqa: ANN401
    """Execute func with exponential-backoff retries.

    See retry_with_exponential_backoff for parameter semantics.
    """
    for attempt in range(max_retries + 1):
        try:
            result = func(*args, **kwargs)
        except exceptions as e:
            delay = _get_retry_delay(
                e,
                attempt,
                max_retries,
                retry_predicate,
                prefix,
                logger_instance,
                base_delay,
                multiplier,
                60.0,
                jitter,
            )
            if delay is not None:
                time.sleep(delay)
                continue
            # Give-up log is emitted inside _get_retry_delay so all retry
            # helpers share the same exhaustion signal.
            raise
        if attempt > 0:
            logger_instance.info(
                "Successfully completed '%s' after %d retry attempt(s)",
                func.__name__,
                attempt,
            )
        return result
    return None  # unreachable: range(max_retries + 1) is non-empty


def retry_with_exponential_backoff(
    max_retries: int,
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
        def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            return _invoke_with_retries(
                func,
                args,
                kwargs,
                max_retries=max_retries,
                base_delay=base_delay,
                multiplier=multiplier,
                jitter=jitter,
                exceptions=exceptions,
                logger_instance=logger_instance,
                prefix=prefix,
                retry_predicate=retry_predicate,
            )

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
                   Defaults to (RequestsConnectionError, HTTPError, Timeout, OSError)
        retry_predicate: Optional callable to determine if exception should trigger retry.
                        If only exceptions list provided, retry on those exceptions.
                        If only predicate provided, use predicate (catch all exceptions).
                        If both provided, first filter by exceptions then check predicate.
        logger_instance: Optional logger for retry events

    Environment variables (using prefix):
        {prefix}_MAX_RETRIES: Maximum retry attempts (default: 3)
        {prefix}_BASE_DELAY: Initial delay in seconds (default: 1.0)
        {prefix}_MULTIPLIER: Backoff multiplier (default: 2.0)
        {prefix}_JITTER: Enable jitter true/false (default: true)

    Returns:
        Configured retry decorator
    """
    # Handle different combinations of exceptions and predicate
    if exceptions is None and retry_predicate is None:
        # Default case: use specific exceptions with is_retryable_error predicate
        exceptions = (RequestsConnectionError, HTTPError, Timeout, OSError)
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
    if base_delay <= 0:
        raise ValueError(f"{prefix}_BASE_DELAY must be > 0")
    if multiplier <= 0:
        raise ValueError(f"{prefix}_MULTIPLIER must be > 0")

    if logger_instance is None:
        logger_instance = logger

    return retry_with_exponential_backoff(
        max_retries=max_retries,
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
# - PLATFORM_SERVICE_BASE_DELAY (default: 1.0s)
# - PLATFORM_SERVICE_MULTIPLIER (default: 2.0)
# - PLATFORM_SERVICE_JITTER (default: true)
retry_platform_service_call = create_retry_decorator("PLATFORM_SERVICE")

# Retry configured through below envs.
# - PROMPT_SERVICE_MAX_RETRIES (default: 3)
# - PROMPT_SERVICE_BASE_DELAY (default: 1.0s)
# - PROMPT_SERVICE_MULTIPLIER (default: 2.0)
# - PROMPT_SERVICE_JITTER (default: true)
retry_prompt_service_call = create_retry_decorator("PROMPT_SERVICE")
