"""Retry Logic and Circuit Breaker Implementation

Provides robust retry mechanisms and circuit breaker patterns for worker operations.
"""

import functools
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any

from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    backoff_strategy: str = "exponential"  # 'exponential', 'linear', 'fixed'
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)


class RetryHandler:
    """Configurable retry handler with multiple backoff strategies.

    Supports:
    - Exponential backoff with jitter
    - Linear backoff
    - Fixed delay
    - Custom exception filtering
    - Retry attempt logging
    """

    def __init__(self, config: RetryConfig | None = None):
        """Initialize retry handler.

        Args:
            config: Retry configuration. Uses defaults if None.
        """
        self.config = config or RetryConfig()

    def __call__(self, func: Callable) -> Callable:
        """Decorator to add retry logic to a function."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.execute_with_retry(func, *args, **kwargs)

        return wrapper

    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Last exception if all retries failed
        """
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                logger.debug(
                    f"Executing {func.__name__}, attempt {attempt}/{self.config.max_attempts}"
                )
                result = func(*args, **kwargs)

                if attempt > 1:
                    logger.info(
                        f"Function {func.__name__} succeeded on attempt {attempt}"
                    )

                return result

            except Exception as e:
                last_exception = e

                # Check if exception is retryable
                if not isinstance(e, self.config.retryable_exceptions):
                    logger.warning(f"Non-retryable exception in {func.__name__}: {e}")
                    raise

                # Don't retry on last attempt
                if attempt == self.config.max_attempts:
                    logger.error(
                        f"Function {func.__name__} failed after {attempt} attempts: {e}"
                    )
                    break

                # Calculate delay
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"Function {func.__name__} failed on attempt {attempt}: {e}. Retrying in {delay:.2f}s"
                )

                time.sleep(delay)

        # All retries exhausted
        raise last_exception

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt."""
        if self.config.backoff_strategy == "exponential":
            delay = self.config.base_delay * (
                self.config.exponential_base ** (attempt - 1)
            )
        elif self.config.backoff_strategy == "linear":
            delay = self.config.base_delay * attempt
        else:  # fixed
            delay = self.config.base_delay

        # Apply maximum delay limit
        delay = min(delay, self.config.max_delay)

        # Add jitter to prevent thundering herd
        if self.config.jitter:
            delay *= 0.5 + random.random() * 0.5  # 50-100% of calculated delay

        return delay


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: type[Exception] = Exception
    success_threshold: int = 3  # Successes needed to close circuit in half-open state


class CircuitBreaker:
    """Circuit breaker implementation to prevent cascading failures.

    States:
    - CLOSED: Normal operation, counting failures
    - OPEN: Rejecting calls, waiting for recovery timeout
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(self, config: CircuitBreakerConfig | None = None):
        """Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration. Uses defaults if None.
        """
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self._lock = Lock()

    def __call__(self, func: Callable) -> Callable:
        """Decorator to add circuit breaker to a function."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)

        return wrapper

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If function fails
        """
        with self._lock:
            current_state = self.state

            # Check if circuit should transition to half-open
            if current_state == CircuitBreakerState.OPEN:
                if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.success_count = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    current_state = CircuitBreakerState.HALF_OPEN
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is OPEN. Recovery timeout: {self.config.recovery_timeout}s"
                    )

        try:
            # Execute function
            logger.debug(
                f"Executing {func.__name__} with circuit breaker in {current_state.value} state"
            )
            result = func(*args, **kwargs)

            # Handle success
            with self._lock:
                if self.state == CircuitBreakerState.HALF_OPEN:
                    self.success_count += 1
                    if self.success_count >= self.config.success_threshold:
                        self.state = CircuitBreakerState.CLOSED
                        self.failure_count = 0
                        logger.info("Circuit breaker CLOSED after successful recovery")
                elif self.state == CircuitBreakerState.CLOSED:
                    self.failure_count = 0  # Reset failure count on success

            return result

        except Exception as e:
            # Handle failure
            if isinstance(e, self.config.expected_exception):
                with self._lock:
                    if self.state == CircuitBreakerState.HALF_OPEN:
                        # Failed during recovery test - back to open
                        self.state = CircuitBreakerState.OPEN
                        self.last_failure_time = time.time()
                        logger.warning(
                            "Circuit breaker back to OPEN after failed recovery test"
                        )
                    elif self.state == CircuitBreakerState.CLOSED:
                        self.failure_count += 1
                        if self.failure_count >= self.config.failure_threshold:
                            self.state = CircuitBreakerState.OPEN
                            self.last_failure_time = time.time()
                            logger.warning(
                                f"Circuit breaker OPENED after {self.failure_count} failures"
                            )

            raise

    def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = 0
            logger.info("Circuit breaker manually reset to CLOSED")

    def force_open(self):
        """Manually force circuit breaker to OPEN state."""
        with self._lock:
            self.state = CircuitBreakerState.OPEN
            self.last_failure_time = time.time()
            logger.warning("Circuit breaker manually forced to OPEN")

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self.state

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "time_since_last_failure": time.time() - self.last_failure_time
            if self.last_failure_time
            else 0,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is in OPEN state."""

    pass


class ResilientExecutor:
    """Combines retry logic and circuit breaker for maximum resilience.

    Usage:
        executor = ResilientExecutor(
            retry_config=RetryConfig(max_attempts=3),
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=5)
        )

        @executor
        def unreliable_function():
            # Function that might fail
            pass
    """

    def __init__(
        self,
        retry_config: RetryConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ):
        """Initialize resilient executor.

        Args:
            retry_config: Retry configuration
            circuit_breaker_config: Circuit breaker configuration
        """
        self.retry_handler = RetryHandler(retry_config)
        self.circuit_breaker = CircuitBreaker(circuit_breaker_config)

    def __call__(self, func: Callable) -> Callable:
        """Apply both retry and circuit breaker to function."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Apply circuit breaker first, then retry
            circuit_protected_func = self.circuit_breaker(func)
            return self.retry_handler.execute_with_retry(
                circuit_protected_func, *args, **kwargs
            )

        return wrapper

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with both retry and circuit breaker protection."""
        circuit_protected_func = self.circuit_breaker(func)
        return self.retry_handler.execute_with_retry(
            circuit_protected_func, *args, **kwargs
        )

    def get_stats(self) -> dict:
        """Get combined statistics."""
        return {
            "circuit_breaker": self.circuit_breaker.get_stats(),
            "retry_config": {
                "max_attempts": self.retry_handler.config.max_attempts,
                "base_delay": self.retry_handler.config.base_delay,
                "backoff_strategy": self.retry_handler.config.backoff_strategy,
            },
        }


# Convenience decorators
def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff_strategy: str = "exponential",
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Simple retry decorator.

    Args:
        max_attempts: Maximum retry attempts
        base_delay: Base delay between retries
        backoff_strategy: Backoff strategy ('exponential', 'linear', 'fixed')
        retryable_exceptions: Exceptions to retry on

    Returns:
        Decorated function
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        backoff_strategy=backoff_strategy,
        retryable_exceptions=retryable_exceptions,
    )
    return RetryHandler(config)


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    expected_exception: type[Exception] = Exception,
) -> Callable:
    """Simple circuit breaker decorator.

    Args:
        failure_threshold: Number of failures to open circuit
        recovery_timeout: Seconds to wait before testing recovery
        expected_exception: Exception type that triggers circuit breaker

    Returns:
        Decorated function
    """
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=expected_exception,
    )
    return CircuitBreaker(config)
