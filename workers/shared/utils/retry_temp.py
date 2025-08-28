"""Temporary Retry Utilities to Avoid Circular Imports

Simple circuit breaker implementation to replace patterns imports temporarily.
This avoids circular imports while maintaining functionality.
"""


class CircuitBreakerOpenError(Exception):
    """Circuit breaker is open - too many failures"""

    pass


def circuit_breaker(
    max_failures=5, reset_timeout=60, failure_threshold=None, recovery_timeout=None
):
    """Simple circuit breaker decorator - temporary implementation"""
    # Handle parameter mapping for compatibility
    if failure_threshold is not None:
        max_failures = failure_threshold
    if recovery_timeout is not None:
        reset_timeout = recovery_timeout

    def decorator(func):
        func._failures = 0
        func._last_failure = 0

        def wrapper(*args, **kwargs):
            import time

            current_time = time.time()

            # Reset if timeout has passed
            if current_time - func._last_failure > reset_timeout:
                func._failures = 0

            # Check if circuit is open
            if func._failures >= max_failures:
                raise CircuitBreakerOpenError(f"Circuit breaker open for {func.__name__}")

            try:
                result = func(*args, **kwargs)
                func._failures = 0  # Reset on success
                return result
            except Exception:
                func._failures += 1
                func._last_failure = current_time
                raise

        return wrapper

    return decorator


def retry(max_attempts=3, base_delay=1.0):
    """Simple retry decorator - temporary implementation"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            import random
            import time

            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:  # Don't sleep on last attempt
                        delay = base_delay * (2**attempt) + random.uniform(0, 1)
                        time.sleep(delay)

            # If we get here, all attempts failed
            raise last_exception

        return wrapper

    return decorator
