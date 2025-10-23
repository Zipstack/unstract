import functools
import logging
import os
import time
import uuid

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger()


class UnstractUtils:
    @staticmethod
    def get_env(env_key: str, default: str | None = None, raise_err=False) -> str:
        """Returns the value of an env variable.

        If its empty or None, raises an error

        Args:
            env_key (str): Key to retrieve
            default (Optional[str], optional): Default for env if not defined.
                Defaults to None.
            raise_err (bool, optional): Flag to raise error if not defined.
                Defaults to False.

        Returns:
            str: Value of the env
        """
        env_value = os.environ.get(env_key, default)
        if env_value is None or env_value == "" and raise_err:
            raise RuntimeError(f"Env variable {env_key} is required")
        return env_value

    @staticmethod
    def build_tool_container_name(
        tool_image: str,
        tool_version: str,
        file_execution_id: str,
        retry_count: int | None = None,
    ) -> str:
        tool_name = tool_image.split("/")[-1]
        # To avoid duplicate name collision
        if retry_count:
            unique_suffix = retry_count
        else:
            unique_suffix = uuid.uuid4().hex[:6]

        container_name = f"{tool_name}-{tool_version}-{unique_suffix}-{file_execution_id}"

        # To support limits of container clients like K8s
        if len(container_name) > 63:
            logger.warning(
                f"Container name exceeds 63 char limit for '{container_name}', "
                "truncating to 63 chars. There might be collisions in container names."
                f"Truncated container name: {container_name[:63]}"
            )
        return container_name[:63]


## Static utility functions  ##
def redact_sensitive_string(str_to_redact: str, reveal_length: int = 4) -> str:
    """Hides sensitive information partially. Useful for logging keys.

    Args:
        str_to_redact (str): String to redact

    Returns:
        str: Redacted string
    """
    if reveal_length < 0:
        raise ValueError("Reveal length must be a non-negative integer")

    redacted_length = max(len(str_to_redact) - reveal_length, 0)
    revealed_part = str_to_redact[:reveal_length]
    redacted_part = "x" * redacted_length
    return revealed_part + redacted_part


def _safe_get_env_int(key: str, default: int, validation_logger=None) -> int:
    """Safely get integer from environment variable with validation.

    Args:
        key (str): Environment variable name
        default (int): Default value if invalid or missing
        validation_logger: Logger for warnings (uses module logger if None)

    Returns:
        int: Validated integer value or default

    Raises:
        No exceptions - always returns a valid integer (default on error)
    """
    log = validation_logger or logger
    try:
        value = int(os.getenv(key, str(default)))
        if value < 0:
            raise ValueError(f"{key} must be non-negative, got {value}")
        return value
    except (ValueError, TypeError) as e:
        env_value = os.getenv(key)
        log.warning(
            f"Invalid {key} environment variable '{env_value}': {e}. "
            f"Using default value: {default}"
        )
        return default


def _safe_get_env_float(key: str, default: float, validation_logger=None) -> float:
    """Safely get float from environment variable with validation.

    Args:
        key (str): Environment variable name
        default (float): Default value if invalid or missing
        validation_logger: Logger for warnings (uses module logger if None)

    Returns:
        float: Validated float value or default

    Raises:
        No exceptions - always returns a valid float (default on error)
    """
    log = validation_logger or logger
    try:
        value = float(os.getenv(key, str(default)))
        if value < 0:
            raise ValueError(f"{key} must be non-negative, got {value}")
        return value
    except (ValueError, TypeError) as e:
        env_value = os.getenv(key)
        log.warning(
            f"Invalid {key} environment variable '{env_value}': {e}. "
            f"Using default value: {default}"
        )
        return default


def retry_on_redis_error(
    max_retries: int | None = None, backoff_factor: float | None = None, retry_logger=None
):
    """Decorator to retry Redis operations on transient connection errors.

    This decorator automatically retries Redis operations that fail due to transient
    connection issues like network timeouts or temporary connection loss.

    Args:
        max_retries (int | None): Number of retries after initial attempt. If None, reads from
            REDIS_RETRY_MAX_ATTEMPTS env var (default: 4, total attempts: 5)
        backoff_factor (float | None): Exponential backoff multiplier in seconds. If None,
            reads from REDIS_RETRY_BACKOFF_FACTOR env var (default: 0.5)
            With defaults (4 retries after initial, 0.5s backoff = 5 total attempts):
            - Initial attempt (no delay)
            - 1st retry: 0.5s delay  (cumulative: 0.5s)
            - 2nd retry: 1.0s delay  (cumulative: 1.5s)
            - 3rd retry: 2.0s delay  (cumulative: 3.5s)
            - 4th retry: 4.0s delay  (cumulative: 7.5s)
            Total: 5 attempts over 7.5 seconds
        retry_logger: Logger instance for warnings (optional, uses module logger if None)

    Environment Variables:
        REDIS_RETRY_MAX_ATTEMPTS (int): Retries after initial attempt (default: 4, total attempts: 5)
        REDIS_RETRY_BACKOFF_FACTOR (float): Exponential backoff multiplier (default: 0.5)

    Retries on:
        - redis.exceptions.ConnectionError: Connection failures
        - redis.exceptions.TimeoutError: Request timeouts

    Does NOT retry on:
        - redis.exceptions.DataError: Invalid data type
        - redis.exceptions.ResponseError: Redis command errors
        (These are application logic errors, not transient failures)

    Example:
        # Use env var defaults (5 retries, 0.5s backoff)
        @retry_on_redis_error(retry_logger=logger)
        def get_data_from_redis(self, key):
            return self.redis_client.get(key)

        # Override defaults
        @retry_on_redis_error(max_retries=3, backoff_factor=0.2, retry_logger=logger)
        def get_critical_data(self, key):
            return self.redis_client.get(key)

    Returns:
        Decorated function with automatic retry logic
    """
    # Read from env vars if not explicitly provided, with validation
    if max_retries is None:
        max_retries = _safe_get_env_int("REDIS_RETRY_MAX_ATTEMPTS", 4, retry_logger)
    if backoff_factor is None:
        backoff_factor = _safe_get_env_float(
            "REDIS_RETRY_BACKOFF_FACTOR", 0.5, retry_logger
        )

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            log = retry_logger or logger
            for attempt in range(max_retries + 1):  # Initial attempt + N retries
                try:
                    return func(*args, **kwargs)
                except (RedisConnectionError, RedisTimeoutError) as e:
                    if attempt == max_retries:  # Last retry exhausted
                        # Final attempt failed, re-raise the exception
                        log.exception(
                            f"Redis operation {func.__name__} failed after {max_retries + 1} total attempts"
                        )
                        raise
                    # Calculate exponential backoff delay
                    delay = backoff_factor * (2**attempt)
                    log.warning(
                        f"Redis transient error in {func.__name__}, "
                        f"retry {attempt + 1}/{max_retries} after {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
            return None

        return wrapper

    return decorator
