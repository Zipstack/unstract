"""Database Retry Utility

A simple, focused utility for retrying Django ORM operations that fail due to
connection issues. Designed for use in models, views, services, and anywhere
database operations might encounter connection drops.

Features:
- Automatic connection pool refresh for stale connections
- Extended retry logic for database unavailable scenarios
- Centralized error classification and handling
- Environment variable configuration
- Multiple usage patterns: decorators, context managers, direct calls

Usage Examples:

    # Decorator usage
    @db_retry(max_retries=3)
    def my_database_operation():
        Model.objects.create(...)

    # Context manager usage
    with db_retry_context(max_retries=3):
        model.save()
        other_model.delete()

    # Direct function usage
    result = retry_database_operation(
        lambda: MyModel.objects.filter(...).update(...),
        max_retries=3
    )
"""

import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any

from django.db import close_old_connections
from django.db.utils import InterfaceError, OperationalError

from utils.db_constants import (
    DatabaseErrorPatterns,
    DatabaseErrorType,
    LogMessages,
    RetryConfiguration,
)

logger = logging.getLogger(__name__)


# Legacy function for backward compatibility - now delegates to RetryConfiguration
def get_retry_setting(setting_name: str, default_value):
    """Get retry setting from Django settings or environment variables with fallback to default.

    Args:
        setting_name: The setting name to look for
        default_value: Default value if setting is not found

    Returns:
        The setting value (int or float based on default_value type)
    """
    return RetryConfiguration.get_setting_value(setting_name, default_value)


def get_default_retry_settings(use_extended=False):
    """Get default retry settings from environment or use built-in defaults.

    Environment variables:
        DB_RETRY_MAX_RETRIES: Maximum number of retry attempts (default: 3 or 8 if extended)
        DB_RETRY_BASE_DELAY: Initial delay between retries in seconds (default: 1.0 or 2.0 if extended)
        DB_RETRY_MAX_DELAY: Maximum delay between retries in seconds (default: 30.0 or 60.0 if extended)
        DB_RETRY_FORCE_REFRESH: Force connection pool refresh on stale connections (default: True)

    Args:
        use_extended: Use extended retry settings for database unavailable scenarios

    Returns:
        dict: Dictionary with retry settings
    """
    return RetryConfiguration.get_retry_settings(use_extended=use_extended)


def _classify_database_error(error: Exception):
    """Classify a database error using centralized error patterns.

    Args:
        error: The exception to classify

    Returns:
        Tuple containing (error_type, needs_refresh, use_extended_retry)
    """
    # Only classify Django database errors
    if not isinstance(error, (OperationalError, InterfaceError)):
        return DatabaseErrorType.NON_CONNECTION_ERROR, False, False

    error_type, needs_refresh = DatabaseErrorPatterns.classify_error(error)

    # For InterfaceError with stale connection patterns, always refresh
    if (
        isinstance(error, InterfaceError)
        and error_type == DatabaseErrorType.STALE_CONNECTION
    ):
        needs_refresh = True

    # Use extended retry for database unavailable scenarios
    use_extended_retry = error_type == DatabaseErrorType.DATABASE_UNAVAILABLE

    return error_type, needs_refresh, use_extended_retry


def _update_retry_settings_for_extended(retry_count: int, use_extended: bool) -> dict:
    """Get extended retry settings if needed for database unavailable errors."""
    if use_extended and retry_count == 0:
        return get_default_retry_settings(use_extended=True)
    return {}


def _handle_connection_pool_refresh(
    error: BaseException, retry_count: int, max_retries: int
) -> None:
    """Handle connection pool refresh for stale connections."""
    logger.warning(
        LogMessages.format_message(
            LogMessages.POOL_CORRUPTION_DETECTED,
            attempt=retry_count,
            total=max_retries + 1,
            error=error,
        )
    )
    try:
        close_old_connections()
        logger.info(LogMessages.POOL_REFRESH_SUCCESS)
    except Exception as refresh_error:
        logger.warning(
            LogMessages.format_message(
                LogMessages.POOL_REFRESH_FAILED, error=refresh_error
            )
        )


def _log_retry_attempt(
    error_type: DatabaseErrorType,
    retry_count: int,
    max_retries: int,
    error: BaseException,
    delay: float,
) -> None:
    """Log retry attempt with appropriate message based on error type."""
    if error_type == DatabaseErrorType.DATABASE_UNAVAILABLE:
        message = LogMessages.DATABASE_UNAVAILABLE_RETRY
    else:
        message = LogMessages.CONNECTION_ERROR_RETRY

    logger.warning(
        LogMessages.format_message(
            message,
            attempt=retry_count,
            total=max_retries + 1,
            error=error,
            delay=delay,
        )
    )


def _handle_retry_attempt(
    error: BaseException,
    error_type: DatabaseErrorType,
    needs_refresh: bool,
    force_refresh: bool,
    retry_count: int,
    max_retries: int,
    delay: float,
) -> None:
    """Handle a single retry attempt - either refresh pool or log retry."""
    if needs_refresh and force_refresh:
        _handle_connection_pool_refresh(error, retry_count, max_retries)
    else:
        _log_retry_attempt(error_type, retry_count, max_retries, error, delay)


def _execute_with_retry(
    operation: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    force_refresh: bool = True,
) -> Any:
    """Execute an operation with retry logic for connection errors.

    Args:
        operation: The operation to execute
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        force_refresh: Whether to force connection pool refresh on stale connections

    Returns:
        The result of the operation

    Raises:
        The original exception if max retries exceeded or non-connection error
    """
    retry_count = 0

    while retry_count <= max_retries:
        try:
            logger.debug(LogMessages.EXECUTING_WITH_RETRY)
            return operation()
        except Exception as e:
            error_type, needs_refresh, use_extended = _classify_database_error(e)

            if not DatabaseErrorPatterns.is_retryable_error(error_type):
                logger.debug(
                    LogMessages.format_message(LogMessages.NON_RETRYABLE_ERROR, error=e)
                )
                raise

            # Update settings for extended retry if needed
            extended_settings = _update_retry_settings_for_extended(
                retry_count, use_extended
            )
            if extended_settings:
                max_retries = extended_settings["max_retries"]
                base_delay = extended_settings["base_delay"]
                max_delay = extended_settings["max_delay"]

            if retry_count < max_retries:
                delay = min(base_delay * (2**retry_count), max_delay)
                retry_count += 1

                _handle_retry_attempt(
                    e,
                    error_type,
                    needs_refresh,
                    force_refresh,
                    retry_count,
                    max_retries,
                    delay,
                )

                time.sleep(delay)
                continue
            else:
                logger.error(
                    LogMessages.format_message(
                        LogMessages.MAX_RETRIES_EXCEEDED, total=max_retries + 1, error=e
                    )
                )
                raise

    # This should never be reached, but included for completeness
    return operation()


def db_retry(
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    force_refresh: bool | None = None,
) -> Callable:
    """Decorator to retry database operations on connection errors.

    Uses environment variables DB_RETRY_MAX_RETRIES, DB_RETRY_BASE_DELAY, DB_RETRY_MAX_DELAY,
    DB_RETRY_FORCE_REFRESH for defaults if parameters are not provided.

    Args:
        max_retries: Maximum number of retry attempts (default from env: DB_RETRY_MAX_RETRIES or 3)
        base_delay: Initial delay between retries in seconds (default from env: DB_RETRY_BASE_DELAY or 1.0)
        max_delay: Maximum delay between retries in seconds (default from env: DB_RETRY_MAX_DELAY or 30.0)
        force_refresh: Force connection pool refresh on stale connections (default from env: DB_RETRY_FORCE_REFRESH or True)

    Returns:
        Decorated function with retry logic

    Example:
        @db_retry(max_retries=5, base_delay=0.5, force_refresh=True)
        def create_user(name, email):
            return User.objects.create(name=name, email=email)

        # Using environment defaults
        @db_retry()
        def save_model(self):
            self.save()
    """
    # Get defaults from environment if not provided
    defaults = get_default_retry_settings()
    final_max_retries = (
        max_retries if max_retries is not None else defaults["max_retries"]
    )
    final_base_delay = base_delay if base_delay is not None else defaults["base_delay"]
    final_max_delay = max_delay if max_delay is not None else defaults["max_delay"]
    final_force_refresh = (
        force_refresh if force_refresh is not None else defaults["force_refresh"]
    )

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            def operation():
                return func(*args, **kwargs)

            return _execute_with_retry(
                operation=operation,
                max_retries=final_max_retries,
                base_delay=final_base_delay,
                max_delay=final_max_delay,
                force_refresh=final_force_refresh,
            )

        return wrapper

    return decorator


def _log_context_non_retryable_error(error: BaseException) -> None:
    """Log non-retryable errors in context manager."""
    logger.debug(LogMessages.format_message(LogMessages.NON_RETRYABLE_ERROR, error=error))


def _log_context_max_retries_exceeded(error: BaseException, total_retries: int) -> None:
    """Log max retries exceeded in context manager."""
    logger.error(
        LogMessages.format_message(
            LogMessages.MAX_RETRIES_EXCEEDED,
            total=total_retries,
            error=error,
        )
    )


def _update_context_retry_settings(
    retry_count: int, use_extended: bool, current_settings: dict
) -> dict:
    """Update retry settings for extended retry if needed."""
    extended_settings = _update_retry_settings_for_extended(retry_count, use_extended)
    if extended_settings:
        return {
            "max_retries": extended_settings["max_retries"],
            "base_delay": extended_settings["base_delay"],
            "max_delay": extended_settings["max_delay"],
            "force_refresh": current_settings["force_refresh"],
        }
    return current_settings


def _handle_context_retry_logic(
    retry_count: int,
    final_max_retries: int,
    final_base_delay: float,
    final_max_delay: float,
    final_force_refresh: bool,
    error: BaseException,
    error_type: DatabaseErrorType,
    needs_refresh: bool,
) -> tuple[int, float]:
    """Handle retry logic for context manager - returns updated retry_count and delay."""
    delay = min(final_base_delay * (2**retry_count), final_max_delay)
    retry_count += 1

    _handle_retry_attempt(
        error,
        error_type,
        needs_refresh,
        final_force_refresh,
        retry_count,
        final_max_retries,
        delay,
    )

    return retry_count, delay


@contextmanager
def db_retry_context(
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    force_refresh: bool | None = None,
):
    """Context manager for retrying database operations on connection errors.

    Uses environment variables DB_RETRY_MAX_RETRIES, DB_RETRY_BASE_DELAY, DB_RETRY_MAX_DELAY,
    DB_RETRY_FORCE_REFRESH for defaults if parameters are not provided.

    Args:
        max_retries: Maximum number of retry attempts (default from env: DB_RETRY_MAX_RETRIES or 3)
        base_delay: Initial delay between retries in seconds (default from env: DB_RETRY_BASE_DELAY or 1.0)
        max_delay: Maximum delay between retries in seconds (default from env: DB_RETRY_MAX_DELAY or 30.0)
        force_refresh: Force connection pool refresh on stale connections (default from env: DB_RETRY_FORCE_REFRESH or True)

    Yields:
        None

    Example:
        with db_retry_context(max_retries=5, force_refresh=True):
            model.save()
            other_model.delete()
            MyModel.objects.filter(...).update(...)
    """
    # Get defaults from environment if not provided
    defaults = get_default_retry_settings()
    current_settings = {
        "max_retries": max_retries
        if max_retries is not None
        else defaults["max_retries"],
        "base_delay": base_delay if base_delay is not None else defaults["base_delay"],
        "max_delay": max_delay if max_delay is not None else defaults["max_delay"],
        "force_refresh": force_refresh
        if force_refresh is not None
        else defaults["force_refresh"],
    }

    retry_count = 0

    while retry_count <= current_settings["max_retries"]:
        try:
            yield
            return  # Success - exit the retry loop
        except Exception as e:
            error_type, needs_refresh, use_extended = _classify_database_error(e)

            if not DatabaseErrorPatterns.is_retryable_error(error_type):
                _log_context_non_retryable_error(e)
                raise

            # Update settings for extended retry if needed
            current_settings = _update_context_retry_settings(
                retry_count, use_extended, current_settings
            )

            if retry_count < current_settings["max_retries"]:
                retry_count, delay = _handle_context_retry_logic(
                    retry_count,
                    current_settings["max_retries"],
                    current_settings["base_delay"],
                    current_settings["max_delay"],
                    current_settings["force_refresh"],
                    e,
                    error_type,
                    needs_refresh,
                )
                time.sleep(delay)
                continue
            else:
                _log_context_max_retries_exceeded(e, current_settings["max_retries"] + 1)
                raise


def retry_database_operation(
    operation: Callable,
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    force_refresh: bool | None = None,
) -> Any:
    """Execute a database operation with retry logic.

    Uses environment variables DB_RETRY_MAX_RETRIES, DB_RETRY_BASE_DELAY, DB_RETRY_MAX_DELAY,
    DB_RETRY_FORCE_REFRESH for defaults if parameters are not provided.

    Args:
        operation: A callable that performs the database operation
        max_retries: Maximum number of retry attempts (default from env: DB_RETRY_MAX_RETRIES or 3)
        base_delay: Initial delay between retries in seconds (default from env: DB_RETRY_BASE_DELAY or 1.0)
        max_delay: Maximum delay between retries in seconds (default from env: DB_RETRY_MAX_DELAY or 30.0)
        force_refresh: Force connection pool refresh on stale connections (default from env: DB_RETRY_FORCE_REFRESH or True)

    Returns:
        The result of the operation

    Example:
        result = retry_database_operation(
            lambda: MyModel.objects.filter(active=True).update(status='processed'),
            max_retries=5,
            force_refresh=True
        )
    """
    # Get defaults from environment if not provided
    defaults = get_default_retry_settings()
    final_max_retries = (
        max_retries if max_retries is not None else defaults["max_retries"]
    )
    final_base_delay = base_delay if base_delay is not None else defaults["base_delay"]
    final_max_delay = max_delay if max_delay is not None else defaults["max_delay"]
    final_force_refresh = (
        force_refresh if force_refresh is not None else defaults["force_refresh"]
    )

    return _execute_with_retry(
        operation=operation,
        max_retries=final_max_retries,
        base_delay=final_base_delay,
        max_delay=final_max_delay,
        force_refresh=final_force_refresh,
    )


# Convenience function with default settings
def quick_retry(operation: Callable) -> Any:
    """Execute a database operation with environment/default retry settings.

    Uses environment variables DB_RETRY_MAX_RETRIES, DB_RETRY_BASE_DELAY, DB_RETRY_MAX_DELAY
    or built-in defaults (3 retries, 1.0s base delay, 30.0s max delay).

    Args:
        operation: A callable that performs the database operation

    Returns:
        The result of the operation

    Example:
        result = quick_retry(lambda: model.save())
    """
    return retry_database_operation(operation)
