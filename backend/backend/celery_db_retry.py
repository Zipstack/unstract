import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from utils.db_constants import (
    DatabaseErrorPatterns,
    DatabaseErrorType,
    LogMessages,
    RetryConfiguration,
)

logger = logging.getLogger(__name__)


def should_use_builtin_retry() -> bool:
    """Check if we should use Celery's built-in retry instead of custom retry.

    Returns:
        bool: True if built-in retry should be used, False for custom retry
    """
    return RetryConfiguration.get_setting_value(
        RetryConfiguration.ENV_CELERY_USE_BUILTIN, False
    )


def _is_sqlalchemy_error(exception: Exception) -> bool:
    """Check if exception is a SQLAlchemy error."""
    try:
        from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError

        return isinstance(exception, SQLAlchemyOperationalError)
    except ImportError:
        return False


def _get_retry_settings_for_error(
    error_type: DatabaseErrorType,
    retry_count: int,
    max_retries: int,
    base_delay: float,
    max_delay: float,
) -> dict:
    """Get appropriate retry settings based on error type."""
    if error_type == DatabaseErrorType.DATABASE_UNAVAILABLE and retry_count == 0:
        extended_settings = RetryConfiguration.get_retry_settings(use_extended=True)
        return {
            "max_retries": extended_settings["max_retries"],
            "base_delay": extended_settings["base_delay"],
            "max_delay": extended_settings["max_delay"],
        }
    return {
        "max_retries": max_retries,
        "base_delay": base_delay,
        "max_delay": max_delay,
    }


def _handle_pool_refresh(
    error: BaseException, retry_count: int, total_retries: int
) -> None:
    """Handle SQLAlchemy connection pool disposal."""
    logger.warning(
        LogMessages.format_message(
            LogMessages.POOL_CORRUPTION_DETECTED,
            attempt=retry_count,
            total=total_retries,
            error=error,
        )
    )
    try:
        _dispose_sqlalchemy_engine()
        logger.info("SQLAlchemy connection pool disposed successfully")
    except Exception as refresh_error:
        logger.warning(
            LogMessages.format_message(
                LogMessages.POOL_REFRESH_FAILED,
                error=refresh_error,
            )
        )


def _log_retry_attempt(
    error_type: DatabaseErrorType,
    retry_count: int,
    total_retries: int,
    error: BaseException,
    delay: float,
) -> None:
    """Log retry attempt with appropriate message."""
    if error_type == DatabaseErrorType.DATABASE_UNAVAILABLE:
        message = LogMessages.DATABASE_UNAVAILABLE_RETRY
    else:
        message = LogMessages.CONNECTION_ERROR_RETRY

    logger.warning(
        LogMessages.format_message(
            message,
            attempt=retry_count,
            total=total_retries,
            error=error,
            delay=delay,
        )
    )


def _handle_non_sqlalchemy_error(error: BaseException) -> None:
    """Handle non-SQLAlchemy errors by logging and re-raising."""
    logger.debug(LogMessages.format_message(LogMessages.NON_RETRYABLE_ERROR, error=error))
    raise


def _handle_non_retryable_error(error: BaseException) -> None:
    """Handle non-retryable errors by logging and re-raising."""
    logger.debug(LogMessages.format_message(LogMessages.NON_RETRYABLE_ERROR, error=error))
    raise


def _execute_retry_attempt(
    error: BaseException,
    error_type: DatabaseErrorType,
    needs_refresh: bool,
    retry_count: int,
    current_settings: dict,
) -> tuple[int, float]:
    """Execute a retry attempt and return updated retry_count and delay."""
    delay = min(
        current_settings["base_delay"] * (2**retry_count),
        current_settings["max_delay"],
    )
    retry_count += 1

    # Handle connection pool refresh if needed
    if needs_refresh:
        _handle_pool_refresh(error, retry_count, current_settings["max_retries"] + 1)
    else:
        _log_retry_attempt(
            error_type,
            retry_count,
            current_settings["max_retries"] + 1,
            error,
            delay,
        )

    return retry_count, delay


def _handle_max_retries_exceeded(error: BaseException, total_retries: int) -> None:
    """Handle the case when max retries are exceeded."""
    logger.error(
        LogMessages.format_message(
            LogMessages.MAX_RETRIES_EXCEEDED,
            total=total_retries,
            error=error,
        )
    )
    raise


def _process_celery_exception(
    error: BaseException,
    retry_count: int,
    max_retries: int,
    base_delay: float,
    max_delay: float,
) -> tuple[int, float] | None:
    """Process a Celery exception and return retry info or None if not retryable.

    Returns:
        tuple[int, float]: (updated_retry_count, delay) if should retry
        None: if should not retry (will re-raise)
    """
    if not _is_sqlalchemy_error(error):
        _handle_non_sqlalchemy_error(error)

    # Use centralized error classification
    error_type, needs_refresh = DatabaseErrorPatterns.classify_error(error)

    if not DatabaseErrorPatterns.is_retryable_error(error_type):
        _handle_non_retryable_error(error)

    # Get appropriate retry settings for this error type
    current_settings = _get_retry_settings_for_error(
        error_type, retry_count, max_retries, base_delay, max_delay
    )

    if retry_count < current_settings["max_retries"]:
        return _execute_retry_attempt(
            error, error_type, needs_refresh, retry_count, current_settings
        )
    else:
        _handle_max_retries_exceeded(error, current_settings["max_retries"] + 1)
        return None  # This line will never be reached due to exception, but added for completeness


def _log_success(retry_count: int) -> None:
    """Log operation success."""
    if retry_count == 0:
        logger.debug(LogMessages.OPERATION_SUCCESS)
    else:
        logger.info(
            LogMessages.format_message(
                LogMessages.OPERATION_SUCCESS_AFTER_RETRY,
                retry_count=retry_count,
            )
        )


def celery_db_retry_with_backoff(
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
):
    """Decorator to retry Celery database backend operations with exponential backoff.

    This is specifically designed for Celery's database result backend operations
    that may experience connection drops when using PgBouncer or database restarts.

    Args:
        max_retries: Maximum number of retry attempts (defaults to settings or 3)
        base_delay: Initial delay in seconds (defaults to settings or 1.0)
        max_delay: Maximum delay in seconds (defaults to settings or 30.0)
    """
    # Get defaults from centralized configuration
    celery_settings = RetryConfiguration.get_celery_retry_settings()

    if max_retries is None:
        max_retries = celery_settings["max_retries"]
    if base_delay is None:
        base_delay = celery_settings["base_delay"]
    if max_delay is None:
        max_delay = celery_settings["max_delay"]

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger.debug(
                LogMessages.format_message(
                    LogMessages.CELERY_OPERATION_START, operation=func.__name__
                )
            )
            retry_count = 0
            while retry_count <= max_retries:
                try:
                    result = func(*args, **kwargs)
                    _log_success(retry_count)
                    return result
                except Exception as e:
                    retry_info = _process_celery_exception(
                        e, retry_count, max_retries, base_delay, max_delay
                    )
                    if retry_info:
                        retry_count, delay = retry_info
                        time.sleep(delay)
                        continue

            # This should never be reached, but included for completeness
            return func(*args, **kwargs)

        return wrapper

    return decorator


def _dispose_sqlalchemy_engine():
    """Dispose SQLAlchemy engine to force connection pool recreation.

    This is called when we detect severe connection issues that require
    the entire connection pool to be recreated.
    """
    try:
        # Try to get the engine from the Celery backend
        from celery import current_app

        backend = current_app.backend
        if hasattr(backend, "engine") and backend.engine:
            backend.engine.dispose()
            logger.info("Disposed SQLAlchemy engine for connection pool refresh")
    except Exception as e:
        logger.warning(f"Could not dispose SQLAlchemy engine: {e}")


# Track if patching has been applied to prevent double patching
_celery_backend_patched = False


def patch_celery_database_backend():
    """Dynamically patch Celery's database backend classes to add retry logic.

    This function should be called during application initialization to add
    connection retry capabilities to Celery's database backend operations.

    Supports hybrid mode: can use either custom retry logic or Celery's built-in retry
    based on CELERY_USE_BUILTIN_RETRY environment variable/setting.
    """
    global _celery_backend_patched

    # Prevent double patching
    if _celery_backend_patched:
        logger.debug("Celery database backend already patched, skipping")
        return

    # Check if we should use built-in retry instead of custom
    if should_use_builtin_retry():
        logger.info(
            "Using Celery's built-in database backend retry (CELERY_USE_BUILTIN_RETRY=true)"
        )
        _configure_builtin_retry()
        _celery_backend_patched = True
        return

    logger.info("Using custom database backend retry (CELERY_USE_BUILTIN_RETRY=false)")

    try:
        from celery.backends.database import DatabaseBackend

        # Check if already patched by looking for our marker attribute
        if hasattr(DatabaseBackend._store_result, "_retry_patched"):
            logger.debug(
                "Celery database backend already patched (detected marker), skipping"
            )
            _celery_backend_patched = True
            return

        # Store original methods - bypass Celery's built-in retry by accessing the real methods
        # This prevents double-retry conflicts when using custom retry
        original_store_result = getattr(
            DatabaseBackend._store_result, "__wrapped__", DatabaseBackend._store_result
        )
        original_get_task_meta_for = getattr(
            DatabaseBackend._get_task_meta_for,
            "__wrapped__",
            DatabaseBackend._get_task_meta_for,
        )
        original_get_result = getattr(
            DatabaseBackend.get_result, "__wrapped__", DatabaseBackend.get_result
        )

        logger.info(
            "Bypassing Celery's built-in retry system to prevent conflicts (using custom retry)"
        )

        # Apply retry decorators
        logger.info("Patching Celery method: _store_result with retry logic")
        DatabaseBackend._store_result = celery_db_retry_with_backoff()(
            original_store_result
        )

        logger.info("Patching Celery method: _get_task_meta_for with retry logic")
        DatabaseBackend._get_task_meta_for = celery_db_retry_with_backoff()(
            original_get_task_meta_for
        )

        logger.info("Patching Celery method: get_result with retry logic")
        DatabaseBackend.get_result = celery_db_retry_with_backoff()(original_get_result)

        # delete_result may not exist in all Celery versions
        if hasattr(DatabaseBackend, "delete_result"):
            logger.info("Patching Celery method: delete_result with retry logic")
            original_delete_result = getattr(
                DatabaseBackend.delete_result,
                "__wrapped__",
                DatabaseBackend.delete_result,
            )
            DatabaseBackend.delete_result = celery_db_retry_with_backoff()(
                original_delete_result
            )
        else:
            logger.info("Celery method delete_result not found, skipping patch")

        # Mark as patched to prevent double patching
        DatabaseBackend._store_result._retry_patched = True
        _celery_backend_patched = True

        logger.info("Successfully patched Celery database backend with retry logic")

    except ImportError as e:
        logger.warning(f"Could not import Celery database backend for patching: {e}")
    except Exception as e:
        logger.error(f"Error patching Celery database backend: {e}")


def _configure_builtin_retry():
    """Configure Celery's built-in database backend retry settings.

    This is called when CELERY_USE_BUILTIN_RETRY=true to setup Celery's
    native retry functionality instead of our custom implementation.
    """
    try:
        import os

        # Get retry configuration from centralized settings
        settings = RetryConfiguration.get_retry_settings()

        max_retries = settings["max_retries"]
        base_delay_ms = int(settings["base_delay"] * 1000)
        max_delay_ms = int(settings["max_delay"] * 1000)

        # Apply built-in retry settings to Celery configuration
        logger.info(
            f"Configured Celery built-in retry: max_retries={max_retries}, base_delay={base_delay_ms}ms, max_delay={max_delay_ms}ms"
        )

        # Store settings for use in celery_config.py
        os.environ["CELERY_RESULT_BACKEND_ALWAYS_RETRY"] = "true"
        os.environ["CELERY_RESULT_BACKEND_MAX_RETRIES"] = str(max_retries)
        os.environ["CELERY_RESULT_BACKEND_BASE_SLEEP_BETWEEN_RETRIES_MS"] = str(
            base_delay_ms
        )
        os.environ["CELERY_RESULT_BACKEND_MAX_SLEEP_BETWEEN_RETRIES_MS"] = str(
            max_delay_ms
        )

        logger.info("Successfully configured Celery's built-in database backend retry")

    except Exception as e:
        logger.error(f"Error configuring Celery built-in retry: {e}")
        logger.warning("Falling back to no retry mechanism")


def get_celery_db_engine_options():
    """Get SQLAlchemy engine options optimized for use with PgBouncer.

    Includes built-in retry configuration if CELERY_USE_BUILTIN_RETRY is enabled.

    These options are designed to work well with PgBouncer connection pooling
    without interfering with PgBouncer's pool management.

    Returns:
        dict: SQLAlchemy engine options
    """
    return {
        # Connection health checking
        "pool_pre_ping": True,  # Test connections before use
        # Minimal pooling (let PgBouncer handle the real pooling)
        "pool_size": 5,  # Small pool since PgBouncer handles real pooling
        "max_overflow": 0,  # No overflow, rely on PgBouncer
        "pool_recycle": 3600,  # Recycle connections every hour
        # Connection timeouts using centralized configuration
        "connect_args": {
            "connect_timeout": RetryConfiguration.get_setting_value(
                "CELERY_DB_CONNECT_TIMEOUT", 30
            ),
        },
        # Echo SQL queries if debug logging is enabled
        "echo": RetryConfiguration.get_setting_value("CELERY_DB_ECHO_SQL", False),
    }
