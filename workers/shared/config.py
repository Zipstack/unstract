"""Worker Configuration Management

Centralized configuration for lightweight workers with environment variable support.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)


@dataclass
class WorkerConfig:
    """Configuration class for lightweight workers.

    Loads configuration from environment variables with sensible defaults.
    Supports validation and type conversion.
    """

    # Internal API Configuration (matches backend patterns)
    internal_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "INTERNAL_API_BASE_URL",
            os.getenv("DJANGO_APP_BACKEND_URL", "http://localhost:8000") + "/internal",
        )
    )
    internal_api_key: str = field(
        default_factory=lambda: os.getenv("INTERNAL_SERVICE_API_KEY", "")
    )

    # Celery Broker Configuration (matches backend/settings/base.py exactly)
    celery_broker_base_url: str = field(
        default_factory=lambda: os.getenv(
            "CELERY_BROKER_BASE_URL", "redis://localhost:6379//"
        )
    )
    celery_broker_user: str = field(
        default_factory=lambda: os.getenv("CELERY_BROKER_USER", "")
    )
    celery_broker_pass: str = field(
        default_factory=lambda: os.getenv("CELERY_BROKER_PASS", "")
    )

    # Database Configuration (for PostgreSQL result backend like backend)
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    db_port: str = field(default_factory=lambda: os.getenv("DB_PORT", "5432"))
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", "unstract_db"))
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "unstract_dev"))
    db_password: str = field(
        default_factory=lambda: os.getenv("DB_PASSWORD", "unstract_pass")
    )

    # Computed URLs (built from components like backend does)
    celery_broker_url: str = field(init=False)
    celery_result_backend: str = field(init=False)

    # Worker Identity
    worker_name: str = field(
        default_factory=lambda: os.getenv("WORKER_NAME", "unstract-worker")
    )
    worker_version: str = field(
        default_factory=lambda: os.getenv("WORKER_VERSION", "1.0.0")
    )
    worker_instance_id: str = field(
        default_factory=lambda: os.getenv("HOSTNAME", "unknown")
    )

    # Organization Context
    organization_id: str | None = field(
        default_factory=lambda: os.getenv("ORGANIZATION_ID")
    )

    # API Client Settings
    api_timeout: int = field(
        default_factory=lambda: int(os.getenv("INTERNAL_API_TIMEOUT", "30"))
    )
    api_retry_attempts: int = field(
        default_factory=lambda: int(os.getenv("INTERNAL_API_RETRY_ATTEMPTS", "3"))
    )
    api_retry_backoff_factor: float = field(
        default_factory=lambda: float(
            os.getenv("INTERNAL_API_RETRY_BACKOFF_FACTOR", "1.0")
        )
    )

    # Logging Configuration
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_format: str = field(default_factory=lambda: os.getenv("LOG_FORMAT", "structured"))
    log_file: str | None = field(default_factory=lambda: os.getenv("LOG_FILE"))

    # Circuit Breaker Settings
    circuit_breaker_failure_threshold: int = field(
        default_factory=lambda: int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
    )
    circuit_breaker_recovery_timeout: int = field(
        default_factory=lambda: int(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "60"))
    )
    circuit_breaker_expected_exception: str = field(
        default_factory=lambda: os.getenv(
            "CIRCUIT_BREAKER_EXPECTED_EXCEPTION", "Exception"
        )
    )

    # Health Check Settings
    health_check_interval: int = field(
        default_factory=lambda: int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))
    )
    health_check_timeout: int = field(
        default_factory=lambda: int(os.getenv("HEALTH_CHECK_TIMEOUT", "10"))
    )

    # Performance Settings
    max_concurrent_tasks: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_TASKS", "10"))
    )
    task_timeout: int = field(
        default_factory=lambda: int(os.getenv("TASK_TIMEOUT", "300"))
    )

    # Monitoring Settings
    enable_metrics: bool = field(
        default_factory=lambda: os.getenv("ENABLE_METRICS", "true").lower() == "true"
    )
    metrics_port: int = field(
        default_factory=lambda: int(os.getenv("METRICS_PORT", "8080"))
    )

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Build broker URL from components (matches backend/settings/base.py pattern)
        if self.celery_broker_base_url:
            if self.celery_broker_user and self.celery_broker_pass:
                # RabbitMQ with authentication
                try:
                    import httpx

                    self.celery_broker_url = str(
                        httpx.URL(self.celery_broker_base_url).copy_with(
                            username=self.celery_broker_user,
                            password=self.celery_broker_pass,
                        )
                    )
                except ImportError:
                    # Fallback if httpx not available
                    from urllib.parse import urlparse, urlunparse

                    parsed = urlparse(self.celery_broker_base_url)
                    parsed = parsed._replace(
                        netloc=f"{self.celery_broker_user}:{self.celery_broker_pass}@{parsed.netloc}"
                    )
                    self.celery_broker_url = urlunparse(parsed)
            else:
                # Redis or broker without authentication
                self.celery_broker_url = self.celery_broker_base_url
        else:
            # Fallback to default Redis
            self.celery_broker_url = "redis://localhost:6379/0"

        # Build PostgreSQL result backend (matches backend/celery_config.py exactly)
        from urllib.parse import quote_plus

        self.celery_result_backend = (
            f"db+postgresql://{self.db_user}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

        self.validate()

    def validate(self):
        """Validate configuration values."""
        errors = []

        # Required fields
        if not self.internal_api_key:
            errors.append("INTERNAL_SERVICE_API_KEY is required")

        if not self.internal_api_base_url:
            errors.append("INTERNAL_API_BASE_URL or DJANGO_APP_BACKEND_URL is required")

        if not self.celery_broker_url:
            errors.append("CELERY_BROKER_BASE_URL is required")

        if not self.celery_result_backend:
            errors.append("Database configuration is required for result backend")

        # Numeric validations
        if self.api_timeout <= 0:
            errors.append("API_TIMEOUT must be positive")

        if self.api_retry_attempts < 0:
            errors.append("API_RETRY_ATTEMPTS must be non-negative")

        if self.api_retry_backoff_factor <= 0:
            errors.append("API_RETRY_BACKOFF_FACTOR must be positive")

        if self.circuit_breaker_failure_threshold <= 0:
            errors.append("CIRCUIT_BREAKER_FAILURE_THRESHOLD must be positive")

        if self.circuit_breaker_recovery_timeout <= 0:
            errors.append("CIRCUIT_BREAKER_RECOVERY_TIMEOUT must be positive")

        # Log level validation
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_log_levels:
            errors.append(f"LOG_LEVEL must be one of {valid_log_levels}")

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            field.name: getattr(self, field.name)
            for field in self.__dataclass_fields__.values()
        }

    def get_log_level(self) -> int:
        """Get numeric log level."""
        return getattr(logging, self.log_level.upper())

    @classmethod
    def from_env(cls, prefix: str = "") -> "WorkerConfig":
        """Create configuration from environment variables with optional prefix.

        Args:
            prefix: Environment variable prefix (e.g., 'WEBHOOK_' for webhook worker)

        Returns:
            WorkerConfig instance
        """
        if prefix and not prefix.endswith("_"):
            prefix += "_"

        # Create a temporary environment with prefixed variables
        original_env = dict(os.environ)

        try:
            # Override with prefixed environment variables
            for key, value in original_env.items():
                if key.startswith(prefix):
                    unprefixed_key = key[len(prefix) :]
                    os.environ[unprefixed_key] = value

            return cls()

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

    def update_from_dict(self, config_dict: dict[str, Any]):
        """Update configuration from dictionary."""
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)

        # Re-validate after updates
        self.validate()

    def get_celery_config(self) -> dict[str, Any]:
        """Get Celery-specific configuration matching backend patterns."""
        return {
            "broker_url": self.celery_broker_url,
            "result_backend": self.celery_result_backend,
            "task_serializer": "json",
            "accept_content": ["json"],
            "result_serializer": "json",
            "timezone": "UTC",
            "enable_utc": True,
            "task_routes": {f"{self.worker_name}.*": {"queue": self.worker_name}},
            "worker_prefetch_multiplier": int(
                os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1")
            ),
            "task_acks_late": os.getenv("CELERY_TASK_ACKS_LATE", "true").lower()
            == "true",
            "worker_max_tasks_per_child": int(
                os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "1000")
            ),
            "task_time_limit": self.task_timeout,
            "task_soft_time_limit": max(30, self.task_timeout - 30),
            "task_reject_on_worker_lost": True,
            "task_acks_on_failure_or_timeout": True,
            "worker_disable_rate_limits": False,
            "task_default_retry_delay": int(
                os.getenv("CELERY_TASK_DEFAULT_RETRY_DELAY", "60")
            ),
            "task_max_retries": int(os.getenv("CELERY_TASK_MAX_RETRIES", "3")),
            "worker_send_task_events": True,
            "task_send_sent_event": True,
            "worker_log_format": "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
            "worker_task_log_format": "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
        }

    def __repr__(self) -> str:
        """String representation masking sensitive values."""
        safe_dict = self.to_dict()
        # Mask sensitive fields
        sensitive_fields = [
            "internal_api_key",
            "celery_broker_pass",
            "celery_broker_url",
            "celery_result_backend",
            "db_password",
        ]
        for field_name in sensitive_fields:
            if field_name in safe_dict and safe_dict[field_name]:
                safe_dict[field_name] = "*" * 8

        return f"WorkerConfig({safe_dict})"
