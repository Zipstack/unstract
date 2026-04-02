"""Exponential Backoff Utilities for Workers

Provides smart retry logic with exponential backoff and circuit breaker patterns
to reduce database load and improve resilience.
"""

import logging
import random
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class ExponentialBackoff:
    """Exponential backoff calculator with jitter and maximum delay."""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 300.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        max_attempts: int = 10,
    ):
        """Initialize exponential backoff calculator.

        Args:
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            backoff_factor: Multiplier for each retry
            jitter: Whether to add random jitter to delays
            max_attempts: Maximum number of attempts before giving up
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.max_attempts = max_attempts

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number.

        Args:
            attempt: Attempt number (1-based)

        Returns:
            Delay in seconds
        """
        if attempt <= 0:
            return 0.0

        # Calculate exponential delay
        delay = self.base_delay * (self.backoff_factor ** (attempt - 1))

        # Apply maximum delay limit
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd
        if self.jitter:
            jitter_range = delay * 0.1  # 10% jitter
            jitter = random.uniform(-jitter_range, jitter_range)
            delay = max(0.1, delay + jitter)  # Minimum 0.1 second delay

        logger.debug(f"Attempt {attempt}: calculated delay {delay:.2f}s")
        return delay

    def should_retry(self, attempt: int) -> bool:
        """Check if should retry for given attempt number.

        Args:
            attempt: Attempt number (1-based)

        Returns:
            True if should retry, False otherwise
        """
        return attempt <= self.max_attempts


class CallbackBackoffManager:
    """Manages exponential backoff specifically for callback pattern optimization."""

    def __init__(self, cache_manager=None):
        """Initialize callback backoff manager.

        Args:
            cache_manager: Optional cache manager for persistent attempt tracking
        """
        self.cache_manager = cache_manager
        self.backoff_configs = {
            "status_check": ExponentialBackoff(
                base_delay=2.0, max_delay=60.0, backoff_factor=1.5, max_attempts=8
            ),
            "pipeline_update": ExponentialBackoff(
                base_delay=1.0, max_delay=30.0, backoff_factor=2.0, max_attempts=5
            ),
            "database_operation": ExponentialBackoff(
                base_delay=0.5, max_delay=10.0, backoff_factor=2.0, max_attempts=6
            ),
            "api_call": ExponentialBackoff(
                base_delay=1.0, max_delay=45.0, backoff_factor=1.8, max_attempts=7
            ),
        }

    def get_delay(
        self, operation_type: str, execution_id: str, organization_id: str = None
    ) -> float:
        """Get backoff delay for specific operation and execution.

        Args:
            operation_type: Type of operation (status_check, pipeline_update, etc.)
            execution_id: Execution ID for tracking attempts
            organization_id: Organization context

        Returns:
            Delay in seconds
        """
        if operation_type not in self.backoff_configs:
            logger.warning(
                f"Unknown operation type: {operation_type}, using default backoff"
            )
            operation_type = "api_call"

        backoff = self.backoff_configs[operation_type]

        # Get attempt count from cache if available
        attempt_count = 1
        if self.cache_manager and self.cache_manager.is_available:
            try:
                cache_key = f"backoff_attempts:{operation_type}:{organization_id or 'global'}:{execution_id}"
                attempt_count = self.cache_manager._redis_client.incr(cache_key)

                # Set expiration on first increment (operation-specific TTL)
                if attempt_count == 1:
                    ttl = 3600 if operation_type == "status_check" else 1800
                    self.cache_manager._redis_client.expire(cache_key, ttl)
            except Exception as e:
                logger.warning(f"Failed to track backoff attempts: {e}")
                attempt_count = 1

        return backoff.calculate_delay(attempt_count)

    def should_retry(
        self, operation_type: str, execution_id: str, organization_id: str = None
    ) -> bool:
        """Check if operation should be retried.

        Args:
            operation_type: Type of operation
            execution_id: Execution ID
            organization_id: Organization context

        Returns:
            True if should retry
        """
        if operation_type not in self.backoff_configs:
            return True

        backoff = self.backoff_configs[operation_type]

        # Get current attempt count
        attempt_count = 1
        if self.cache_manager and self.cache_manager.is_available:
            try:
                cache_key = f"backoff_attempts:{operation_type}:{organization_id or 'global'}:{execution_id}"
                attempt_count = int(self.cache_manager._redis_client.get(cache_key) or 1)
            except Exception:
                pass

        should_retry = backoff.should_retry(attempt_count)
        logger.debug(
            f"Operation {operation_type} attempt {attempt_count}: should_retry={should_retry}"
        )
        return should_retry

    def clear_attempts(
        self, operation_type: str, execution_id: str, organization_id: str = None
    ):
        """Clear attempt counter after successful operation.

        Args:
            operation_type: Type of operation
            execution_id: Execution ID
            organization_id: Organization context
        """
        if not self.cache_manager or not self.cache_manager.is_available:
            return

        try:
            cache_key = f"backoff_attempts:{operation_type}:{organization_id or 'global'}:{execution_id}"
            self.cache_manager._redis_client.delete(cache_key)
            logger.debug(f"Cleared backoff attempts for {operation_type}:{execution_id}")
        except Exception as e:
            logger.warning(f"Failed to clear backoff attempts: {e}")


def with_exponential_backoff(
    operation_type: str = "api_call",
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    give_up_on: tuple = (),
):
    """Decorator for adding exponential backoff to functions.

    Args:
        operation_type: Type of operation for backoff configuration
        max_attempts: Maximum retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Exponential backoff factor
        exceptions: Exception types that trigger retry
        give_up_on: Exception types that should not retry
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            backoff = ExponentialBackoff(
                base_delay=base_delay,
                max_delay=max_delay,
                backoff_factor=backoff_factor,
                max_attempts=max_attempts,
            )

            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)

                    # Success - log if this was a retry
                    if attempt > 1:
                        logger.info(
                            f"Function {func.__name__} succeeded on attempt {attempt}"
                        )

                    return result

                except give_up_on as e:
                    # Don't retry for these exceptions
                    logger.error(
                        f"Function {func.__name__} failed with non-retryable error: {e}"
                    )
                    raise

                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise

                    delay = backoff.calculate_delay(attempt)
                    logger.warning(
                        f"Function {func.__name__} failed on attempt {attempt}/{max_attempts}: {e}. "
                        f"Retrying in {delay:.2f}s"
                    )

                    time.sleep(delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


class SmartRetryManager:
    """Advanced retry manager with circuit breaker and adaptive backoff."""

    def __init__(self, cache_manager=None):
        """Initialize smart retry manager.

        Args:
            cache_manager: Cache manager for persistent state
        """
        self.cache_manager = cache_manager
        self.circuit_breakers = {}

    def execute_with_smart_retry(
        self,
        func: Callable,
        operation_id: str,
        args: tuple = (),
        kwargs: dict = None,
        max_attempts: int = 5,
        circuit_breaker: bool = True,
        **backoff_kwargs,
    ) -> Any:
        """Execute function with smart retry logic.

        Args:
            func: Function to execute
            operation_id: Unique operation identifier
            args: Function arguments
            kwargs: Function keyword arguments
            max_attempts: Maximum retry attempts
            circuit_breaker: Whether to use circuit breaker
            **backoff_kwargs: Backoff configuration

        Returns:
            Function result

        Raises:
            Exception: If all retries fail or circuit breaker is open
        """
        kwargs = kwargs or {}

        # Check circuit breaker
        if circuit_breaker and self._is_circuit_open(operation_id):
            raise Exception(f"Circuit breaker open for operation: {operation_id}")

        backoff = ExponentialBackoff(max_attempts=max_attempts, **backoff_kwargs)

        last_exception = None
        consecutive_failures = 0

        for attempt in range(1, max_attempts + 1):
            try:
                result = func(*args, **kwargs)

                # Success - reset circuit breaker
                if circuit_breaker:
                    self._reset_circuit_breaker(operation_id)

                if attempt > 1:
                    logger.info(
                        f"Operation {operation_id} succeeded on attempt {attempt}"
                    )

                return result

            except Exception as e:
                last_exception = e
                consecutive_failures += 1

                # Update circuit breaker
                if circuit_breaker:
                    self._record_failure(operation_id)

                if attempt == max_attempts:
                    logger.error(
                        f"Operation {operation_id} failed after {max_attempts} attempts: {e}"
                    )
                    break

                delay = backoff.calculate_delay(attempt)
                logger.warning(
                    f"Operation {operation_id} failed on attempt {attempt}/{max_attempts}: {e}. "
                    f"Retrying in {delay:.2f}s"
                )

                time.sleep(delay)

        # All attempts failed
        if circuit_breaker and consecutive_failures >= 3:
            self._open_circuit_breaker(operation_id)

        if last_exception:
            raise last_exception

    def _is_circuit_open(self, operation_id: str) -> bool:
        """Check if circuit breaker is open for operation."""
        if not self.cache_manager or not self.cache_manager.is_available:
            return False

        try:
            cache_key = f"circuit_breaker:{operation_id}"
            state = self.cache_manager._redis_client.get(cache_key)
            return state == "open"
        except Exception:
            return False

    def _open_circuit_breaker(self, operation_id: str, timeout: int = 300):
        """Open circuit breaker for operation."""
        if not self.cache_manager or not self.cache_manager.is_available:
            return

        try:
            cache_key = f"circuit_breaker:{operation_id}"
            self.cache_manager._redis_client.setex(cache_key, timeout, "open")
            logger.warning(f"Opened circuit breaker for operation: {operation_id}")
        except Exception as e:
            logger.warning(f"Failed to open circuit breaker: {e}")

    def _reset_circuit_breaker(self, operation_id: str):
        """Reset circuit breaker after successful operation."""
        if not self.cache_manager or not self.cache_manager.is_available:
            return

        try:
            cache_key = f"circuit_breaker:{operation_id}"
            self.cache_manager._redis_client.delete(cache_key)

            # Also clear failure count
            failure_key = f"circuit_failures:{operation_id}"
            self.cache_manager._redis_client.delete(failure_key)
        except Exception:
            pass

    def _record_failure(self, operation_id: str):
        """Record failure for circuit breaker calculation."""
        if not self.cache_manager or not self.cache_manager.is_available:
            return

        try:
            failure_key = f"circuit_failures:{operation_id}"
            failures = self.cache_manager._redis_client.incr(failure_key)

            # Set expiration on first failure
            if failures == 1:
                self.cache_manager._redis_client.expire(failure_key, 600)  # 10 minutes

            # Open circuit after 5 failures in 10 minutes
            if failures >= 5:
                self._open_circuit_breaker(operation_id, timeout=600)

        except Exception:
            pass


# Global instances
_backoff_manager = None
_retry_manager = None


def get_backoff_manager() -> CallbackBackoffManager | None:
    """Get global backoff manager instance."""
    return _backoff_manager


def get_retry_manager() -> SmartRetryManager | None:
    """Get global retry manager instance."""
    return _retry_manager


def initialize_backoff_managers(cache_manager=None):
    """Initialize global backoff and retry managers."""
    global _backoff_manager, _retry_manager
    _backoff_manager = CallbackBackoffManager(cache_manager)
    _retry_manager = SmartRetryManager(cache_manager)
    return _backoff_manager, _retry_manager
