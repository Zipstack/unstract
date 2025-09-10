"""Database Error Constants and Configuration

Centralized error patterns, types, and configuration for database retry mechanisms.
Used by both Django ORM retry (db_retry.py) and Celery SQLAlchemy retry (celery_db_retry.py).
"""

import os
from dataclasses import dataclass
from enum import Enum


class DatabaseErrorType(Enum):
    """Classification of database connection errors."""

    STALE_CONNECTION = "stale_connection"
    DATABASE_UNAVAILABLE = "database_unavailable"
    TRANSIENT_ERROR = "transient_error"
    NON_CONNECTION_ERROR = "non_connection_error"


class ConnectionPoolType(Enum):
    """Types of connection pools that need different refresh strategies."""

    DJANGO_ORM = "django_orm"
    SQLALCHEMY = "sqlalchemy"


@dataclass(frozen=True)
class ErrorPattern:
    """Defines an error pattern with its classification and handling strategy."""

    keywords: tuple[str, ...]
    error_type: DatabaseErrorType
    requires_pool_refresh: bool
    description: str


class DatabaseErrorPatterns:
    """Centralized database error patterns for consistent classification."""

    # Stale connection patterns - connection exists but is dead
    STALE_CONNECTION_PATTERNS = (
        ErrorPattern(
            keywords=("connection already closed",),
            error_type=DatabaseErrorType.STALE_CONNECTION,
            requires_pool_refresh=True,
            description="Django InterfaceError - connection pool corruption",
        ),
        ErrorPattern(
            keywords=("server closed the connection unexpectedly",),
            error_type=DatabaseErrorType.STALE_CONNECTION,
            requires_pool_refresh=True,
            description="PostgreSQL dropped connection, pool may be stale",
        ),
        ErrorPattern(
            keywords=("connection was lost",),
            error_type=DatabaseErrorType.STALE_CONNECTION,
            requires_pool_refresh=True,
            description="Connection lost during operation",
        ),
    )

    # Database unavailable patterns - database is completely unreachable
    DATABASE_UNAVAILABLE_PATTERNS = (
        ErrorPattern(
            keywords=("connection refused",),
            error_type=DatabaseErrorType.DATABASE_UNAVAILABLE,
            requires_pool_refresh=True,
            description="Database server is down or unreachable",
        ),
        ErrorPattern(
            keywords=("could not connect",),
            error_type=DatabaseErrorType.DATABASE_UNAVAILABLE,
            requires_pool_refresh=True,
            description="Unable to establish database connection",
        ),
        ErrorPattern(
            keywords=("no route to host",),
            error_type=DatabaseErrorType.DATABASE_UNAVAILABLE,
            requires_pool_refresh=True,
            description="Network routing issue to database",
        ),
    )

    # Transient error patterns - temporary issues, retry without pool refresh
    TRANSIENT_ERROR_PATTERNS = (
        ErrorPattern(
            keywords=("connection timeout",),
            error_type=DatabaseErrorType.TRANSIENT_ERROR,
            requires_pool_refresh=False,
            description="Connection attempt timed out",
        ),
        ErrorPattern(
            keywords=("connection pool exhausted",),
            error_type=DatabaseErrorType.TRANSIENT_ERROR,
            requires_pool_refresh=False,
            description="Connection pool temporarily full",
        ),
        ErrorPattern(
            keywords=("connection closed",),
            error_type=DatabaseErrorType.TRANSIENT_ERROR,
            requires_pool_refresh=False,
            description="Connection closed during operation",
        ),
        # MySQL compatibility patterns
        ErrorPattern(
            keywords=("lost connection to mysql server",),
            error_type=DatabaseErrorType.TRANSIENT_ERROR,
            requires_pool_refresh=False,
            description="MySQL connection lost",
        ),
        ErrorPattern(
            keywords=("mysql server has gone away",),
            error_type=DatabaseErrorType.TRANSIENT_ERROR,
            requires_pool_refresh=False,
            description="MySQL server disconnected",
        ),
    )

    # All patterns combined for easy iteration
    ALL_PATTERNS = (
        STALE_CONNECTION_PATTERNS
        + DATABASE_UNAVAILABLE_PATTERNS
        + TRANSIENT_ERROR_PATTERNS
    )

    @classmethod
    def classify_error(
        cls, error: Exception, error_message: str = None
    ) -> tuple[DatabaseErrorType, bool]:
        """Classify a database error and determine if pool refresh is needed.

        Args:
            error: The exception to classify
            error_message: Optional pre-lowercased error message for efficiency

        Returns:
            Tuple[DatabaseErrorType, bool]: (error_type, needs_pool_refresh)
        """
        if error_message is None:
            error_message = str(error).lower()
        else:
            error_message = error_message.lower()

        # Check all patterns for matches
        for pattern in cls.ALL_PATTERNS:
            if any(keyword in error_message for keyword in pattern.keywords):
                return pattern.error_type, pattern.requires_pool_refresh

        # No pattern matched
        return DatabaseErrorType.NON_CONNECTION_ERROR, False

    @classmethod
    def is_retryable_error(cls, error_type: DatabaseErrorType) -> bool:
        """Check if an error type should be retried."""
        return error_type in {
            DatabaseErrorType.STALE_CONNECTION,
            DatabaseErrorType.DATABASE_UNAVAILABLE,
            DatabaseErrorType.TRANSIENT_ERROR,
        }

    @classmethod
    def get_all_error_keywords(cls) -> list[str]:
        """Get all error keywords as a flat list (for backward compatibility)."""
        keywords = []
        for pattern in cls.ALL_PATTERNS:
            keywords.extend(pattern.keywords)
        return keywords


class RetryConfiguration:
    """Centralized configuration for database retry settings."""

    # Environment variable names
    ENV_MAX_RETRIES = "DB_RETRY_MAX_RETRIES"
    ENV_BASE_DELAY = "DB_RETRY_BASE_DELAY"
    ENV_MAX_DELAY = "DB_RETRY_MAX_DELAY"
    ENV_FORCE_REFRESH = "DB_RETRY_FORCE_REFRESH"

    # Celery-specific environment variables
    ENV_CELERY_USE_BUILTIN = "CELERY_USE_BUILTIN_RETRY"
    ENV_CELERY_MAX_RETRIES = "CELERY_DB_RETRY_COUNT"
    ENV_CELERY_BASE_DELAY = "CELERY_DB_RETRY_DELAY"
    ENV_CELERY_MAX_DELAY = "CELERY_DB_RETRY_MAX_DELAY"

    # Default values
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BASE_DELAY = 1.0
    DEFAULT_MAX_DELAY = 30.0
    DEFAULT_FORCE_REFRESH = True

    # Extended retry for database unavailable scenarios
    DEFAULT_EXTENDED_MAX_RETRIES = 8
    DEFAULT_EXTENDED_BASE_DELAY = 2.0
    DEFAULT_EXTENDED_MAX_DELAY = 60.0

    @classmethod
    def get_setting_value(cls, setting_name: str, default_value, use_django=True):
        """Get setting value from Django settings or environment with proper type conversion.

        Args:
            setting_name: Name of the setting
            default_value: Default value (determines return type)
            use_django: Whether to try Django settings first

        Returns:
            Setting value converted to same type as default_value
        """
        # Try Django settings first (if available and requested)
        if use_django:
            try:
                from django.conf import settings
                from django.core.exceptions import ImproperlyConfigured

                if hasattr(settings, setting_name):
                    return getattr(settings, setting_name)
            except (ImportError, ImproperlyConfigured):
                # Django not available or not configured
                pass

        # Fall back to environment variables
        env_value = os.environ.get(setting_name)
        if env_value is not None:
            return cls._convert_env_value(env_value, default_value)

        return default_value

    @classmethod
    def _convert_env_value(cls, env_value: str, default_value):
        """Convert environment variable string to appropriate type."""
        try:
            # Check bool first since bool is subclass of int in Python
            if isinstance(default_value, bool):
                return env_value.lower() in ("true", "1", "yes", "on")
            elif isinstance(default_value, int):
                return int(env_value)
            elif isinstance(default_value, float):
                return float(env_value)
            else:
                return env_value
        except (ValueError, TypeError):
            return default_value

    @classmethod
    def get_retry_settings(cls, use_extended=False, use_django=True) -> dict:
        """Get complete retry configuration.

        Args:
            use_extended: Use extended settings for database unavailable scenarios
            use_django: Whether to check Django settings

        Returns:
            Dict with retry configuration
        """
        if use_extended:
            max_retries_default = cls.DEFAULT_EXTENDED_MAX_RETRIES
            base_delay_default = cls.DEFAULT_EXTENDED_BASE_DELAY
            max_delay_default = cls.DEFAULT_EXTENDED_MAX_DELAY
        else:
            max_retries_default = cls.DEFAULT_MAX_RETRIES
            base_delay_default = cls.DEFAULT_BASE_DELAY
            max_delay_default = cls.DEFAULT_MAX_DELAY

        return {
            "max_retries": cls.get_setting_value(
                cls.ENV_MAX_RETRIES, max_retries_default, use_django
            ),
            "base_delay": cls.get_setting_value(
                cls.ENV_BASE_DELAY, base_delay_default, use_django
            ),
            "max_delay": cls.get_setting_value(
                cls.ENV_MAX_DELAY, max_delay_default, use_django
            ),
            "force_refresh": cls.get_setting_value(
                cls.ENV_FORCE_REFRESH, cls.DEFAULT_FORCE_REFRESH, use_django
            ),
        }

    @classmethod
    def get_celery_retry_settings(cls, use_django=True) -> dict:
        """Get Celery-specific retry configuration."""
        return {
            "max_retries": cls.get_setting_value(
                cls.ENV_CELERY_MAX_RETRIES, cls.DEFAULT_MAX_RETRIES, use_django
            ),
            "base_delay": cls.get_setting_value(
                cls.ENV_CELERY_BASE_DELAY, cls.DEFAULT_BASE_DELAY, use_django
            ),
            "max_delay": cls.get_setting_value(
                cls.ENV_CELERY_MAX_DELAY, cls.DEFAULT_MAX_DELAY, use_django
            ),
            "use_builtin": cls.get_setting_value(
                cls.ENV_CELERY_USE_BUILTIN, False, use_django
            ),
        }


class LogMessages:
    """Centralized log message templates for consistent logging."""

    # Success messages
    OPERATION_SUCCESS = "Operation completed successfully"
    OPERATION_SUCCESS_AFTER_RETRY = (
        "Operation succeeded after {retry_count} retry attempts"
    )

    # Connection pool refresh messages
    POOL_CORRUPTION_DETECTED = "Database connection pool corruption detected (attempt {attempt}/{total}): {error}. Refreshing connection pool..."
    POOL_REFRESH_SUCCESS = "Connection pool refreshed successfully"
    POOL_REFRESH_FAILED = "Failed to refresh connection pool: {error}"

    # Retry attempt messages
    CONNECTION_ERROR_RETRY = "Database connection error (attempt {attempt}/{total}): {error}. Retrying in {delay} seconds..."
    DATABASE_UNAVAILABLE_RETRY = "Database unavailable (attempt {attempt}/{total}): {error}. Using extended retry in {delay} seconds..."

    # Failure messages
    MAX_RETRIES_EXCEEDED = "Database connection failed after {total} attempts: {error}"
    NON_RETRYABLE_ERROR = "Non-retryable error, not retrying: {error}"

    # Execution messages
    EXECUTING_WITH_RETRY = "Executing operation with retry logic..."
    CELERY_OPERATION_START = (
        "Executing Celery DB operation: {operation} (retry mechanism active)"
    )

    @classmethod
    def format_message(cls, template: str, **kwargs) -> str:
        """Format a log message template with provided kwargs."""
        return template.format(**kwargs)
