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


# Configuration Constants Classes
class DefaultConfig:
    """Default configuration values for workers."""

    # Task timeouts (in seconds) - Higher defaults for production stability
    DEFAULT_TASK_TIMEOUT = 7200  # 2 hours - safer for complex workflows
    DEFAULT_TASK_SOFT_TIMEOUT = 6300  # 1h 45m (gives 15 minutes for cleanup)
    FILE_PROCESSING_TIMEOUT = 7200  # 2 hours - handles large files and complex processing
    FILE_PROCESSING_SOFT_TIMEOUT = 6300  # 1h 45m (gives 15 minutes for cleanup)
    CALLBACK_TIMEOUT = 3600  # 1 hour - callbacks are usually faster
    CALLBACK_SOFT_TIMEOUT = 3300  # 55 minutes (gives 5 minutes for cleanup)
    WEBHOOK_TIMEOUT = 30  # 30 seconds (keep short for webhooks)

    # Retry configuration
    DEFAULT_MAX_RETRIES = 3
    FILE_PROCESSING_MAX_RETRIES = 5
    CALLBACK_MAX_RETRIES = 8
    WEBHOOK_MAX_RETRIES = 3

    # Performance limits
    MAX_CONCURRENT_TASKS = 10
    MAX_FILE_BATCH_SIZE = 20
    MAX_PARALLEL_FILE_BATCHES = 4
    MAX_MEMORY_USAGE_MB = 2048

    # Cache settings
    DEFAULT_CACHE_TTL = 60  # 1 minute
    EXECUTION_STATUS_CACHE_TTL = 30  # 30 seconds
    PIPELINE_STATUS_CACHE_TTL = 60  # 1 minute
    BATCH_SUMMARY_CACHE_TTL = 90  # 90 seconds

    # Health check intervals
    HEALTH_CHECK_INTERVAL = 30  # 30 seconds
    METRICS_COLLECTION_INTERVAL = 60  # 1 minute

    # File processing limits
    MAX_FILE_SIZE_MB = 100
    DEFAULT_FILE_PATTERNS = ["*"]
    MAX_FILES_PER_EXECUTION = 1000

    # API client settings
    API_REQUEST_TIMEOUT = 30
    API_RETRY_ATTEMPTS = 3
    API_RETRY_BACKOFF_FACTOR = 1.0


class QueueConfig:
    """Queue routing and configuration."""

    # Queue routing rules
    TASK_ROUTES = {
        "send_webhook_notification": {
            "queue": "notifications"
        },  # Route to notification worker
        "async_execute_bin_api": {"queue": "general"},
        "execute_workflow_with_files": {"queue": "general"},
        "_orchestrate_file_processing_general": {"queue": "general"},
        "process_file_batch": {"queue": "file_processing"},
        "execute_single_file": {"queue": "file_processing"},
        "update_file_execution_status": {"queue": "file_processing"},
        "process_batch_callback": {"queue": "callback"},
        "update_workflow_execution_status": {"queue": "callback"},
        "update_pipeline_status": {"queue": "callback"},
        "deploy_api_workflow": {"queue": "api_deployments"},
        "undeploy_api_workflow": {"queue": "api_deployments"},
        "check_api_deployment_status": {"queue": "api_deployments"},
        # Scheduler tasks routing
        "scheduler.tasks.execute_pipeline_task": {"queue": "scheduler"},
    }

    # Queue priorities (higher number = higher priority)
    QUEUE_PRIORITIES = {
        "callback": 9,  # Highest priority for completion callbacks
        "webhook": 8,  # High priority for notifications
        "scheduler": 6,  # High priority for scheduled tasks
        "general": 5,  # Standard priority for orchestration
        "file_processing": 3,  # Lower priority for file processing
        "api_deployments": 2,  # Lowest priority for deployments
    }

    # Queue-specific worker settings
    QUEUE_WORKER_SETTINGS = {
        "general": {
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 1000,
        },
        "file_processing": {
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 100,  # Lower due to memory usage
        },
        "callback": {
            "prefetch_multiplier": 2,
            "max_tasks_per_child": 2000,
        },
        "api_deployments": {
            "prefetch_multiplier": 1,
            "max_tasks_per_child": 500,
        },
    }


class FileProcessingConfig:
    """File processing specific configuration."""

    # Supported file types
    SUPPORTED_MIME_TYPES = [
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/json",
        "application/xml",
        "text/xml",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/bmp",
        "image/tiff",
    ]

    # File size limits (in bytes)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    MIN_FILE_SIZE = 1  # 1 byte

    # Batch processing limits
    MIN_BATCH_SIZE = 1
    MAX_BATCH_SIZE = 20
    DEFAULT_BATCH_SIZE = 5

    # Processing timeouts
    SINGLE_FILE_TIMEOUT = 300  # 5 minutes per file
    BATCH_TIMEOUT = 1800  # 30 minutes per batch

    # Retry configuration for file operations
    FILE_RETRY_MAX_ATTEMPTS = 3
    FILE_RETRY_BACKOFF_FACTOR = 2.0
    FILE_RETRY_MAX_DELAY = 60  # 1 minute


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

    # Celery Backend Database Configuration (with CELERY_BACKEND_ prefix)
    celery_backend_db_host: str = field(
        default_factory=lambda: os.getenv(
            "CELERY_BACKEND_DB_HOST", os.getenv("DB_HOST", "localhost")
        )  # Fallback to main DB config
    )
    celery_backend_db_port: str = field(
        default_factory=lambda: os.getenv(
            "CELERY_BACKEND_DB_PORT", os.getenv("DB_PORT", "5432")
        )
    )
    celery_backend_db_name: str = field(
        default_factory=lambda: os.getenv(
            "CELERY_BACKEND_DB_NAME", os.getenv("DB_NAME", "unstract_db")
        )
    )
    celery_backend_db_user: str = field(
        default_factory=lambda: os.getenv(
            "CELERY_BACKEND_DB_USER", os.getenv("DB_USER", "unstract_dev")
        )
    )
    celery_backend_db_password: str = field(
        default_factory=lambda: os.getenv(
            "CELERY_BACKEND_DB_PASSWORD", os.getenv("DB_PASSWORD", "unstract_pass")
        )
    )
    celery_backend_db_schema: str = field(
        default_factory=lambda: os.getenv("CELERY_BACKEND_DB_SCHEMA", "public")
    )

    # Redis Cache Configuration (separate from Celery broker)
    cache_redis_enabled: bool = field(
        default_factory=lambda: os.getenv("CACHE_REDIS_ENABLED", "true").lower() == "true"
    )
    cache_redis_host: str = field(
        default_factory=lambda: os.getenv(
            "CACHE_REDIS_HOST", os.getenv("REDIS_HOST", "localhost")
        )
    )
    cache_redis_port: int = field(
        default_factory=lambda: int(
            os.getenv("CACHE_REDIS_PORT", os.getenv("REDIS_PORT", "6379"))
        )
    )
    cache_redis_db: int = field(
        default_factory=lambda: int(
            os.getenv("CACHE_REDIS_DB", os.getenv("REDIS_DB", "1"))
        )  # Default to DB 1 (separate from Celery DB 0)
    )
    cache_redis_password: str = field(
        default_factory=lambda: os.getenv(
            "CACHE_REDIS_PASSWORD", os.getenv("REDIS_PASSWORD", "")
        )
    )
    cache_redis_username: str = field(
        default_factory=lambda: os.getenv("CACHE_REDIS_USERNAME", "")
    )
    cache_redis_ssl: bool = field(
        default_factory=lambda: os.getenv("CACHE_REDIS_SSL", "false").lower() == "true"
    )
    cache_redis_ssl_cert_reqs: str = field(
        default_factory=lambda: os.getenv("CACHE_REDIS_SSL_CERT_REQS", "required")
    )

    # Computed URLs (built from components like backend does)
    celery_broker_url: str = field(init=False)
    celery_result_backend: str = field(init=False)
    cache_redis_url: str = field(init=False)

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

    # Task Timeout Settings (in seconds) - 1 hour defaults
    task_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("TASK_TIMEOUT", str(DefaultConfig.DEFAULT_TASK_TIMEOUT))
        )
    )
    task_soft_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("TASK_SOFT_TIMEOUT", str(DefaultConfig.DEFAULT_TASK_SOFT_TIMEOUT))
        )
    )

    # File Processing Task Timeouts
    file_processing_timeout: int = field(
        default_factory=lambda: int(
            os.getenv(
                "FILE_PROCESSING_TIMEOUT", str(DefaultConfig.FILE_PROCESSING_TIMEOUT)
            )
        )
    )
    file_processing_soft_timeout: int = field(
        default_factory=lambda: int(
            os.getenv(
                "FILE_PROCESSING_SOFT_TIMEOUT",
                str(DefaultConfig.FILE_PROCESSING_SOFT_TIMEOUT),
            )
        )
    )

    # Callback Task Timeouts
    callback_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("CALLBACK_TIMEOUT", str(DefaultConfig.CALLBACK_TIMEOUT))
        )
    )
    callback_soft_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("CALLBACK_SOFT_TIMEOUT", str(DefaultConfig.CALLBACK_SOFT_TIMEOUT))
        )
    )

    # Webhook Task Timeouts (kept shorter for webhooks)
    webhook_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("WEBHOOK_TIMEOUT", str(DefaultConfig.WEBHOOK_TIMEOUT))
        )
    )

    # Workflow-Level Timeout Management (prevents timeout mismatches)
    workflow_total_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("WORKFLOW_TOTAL_TIMEOUT", str(DefaultConfig.DEFAULT_TASK_TIMEOUT))
        )
    )
    callback_min_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("CALLBACK_MIN_TIMEOUT", "300")
        )  # 5 minutes minimum
    )

    # Backward compatibility mode - enables gradual migration from old backend workers
    enable_coordinated_timeouts: bool = field(
        default_factory=lambda: os.getenv("ENABLE_COORDINATED_TIMEOUTS", "true").lower()
        == "true"
    )

    # Monitoring Settings
    enable_metrics: bool = field(
        default_factory=lambda: os.getenv("ENABLE_METRICS", "true").lower() == "true"
    )
    enable_health_server: bool = field(
        default_factory=lambda: os.getenv("ENABLE_HEALTH_SERVER", "true").lower()
        == "true"
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

        # Build PostgreSQL result backend with configurable schema support
        from urllib.parse import quote_plus

        self.celery_result_backend = (
            f"db+postgresql://{self.celery_backend_db_user}:{quote_plus(self.celery_backend_db_password)}"
            f"@{self.celery_backend_db_host}:{self.celery_backend_db_port}/"
            f"{self.celery_backend_db_name}"
        )

        # Add schema parameter if not using default 'public' schema
        if self.celery_backend_db_schema != "public":
            self.celery_result_backend += (
                f"?options=-csearch_path%3D{self.celery_backend_db_schema}"
            )

        # Build Redis cache URL for separate cache instance
        self._build_cache_redis_url()

        self.validate()

    def _build_cache_redis_url(self):
        """Build Redis cache URL from configuration components."""
        if not self.cache_redis_enabled:
            self.cache_redis_url = ""
            return

        # Build Redis URL with all authentication and SSL options
        scheme = "rediss" if self.cache_redis_ssl else "redis"

        # Build authentication part
        auth_part = ""
        if self.cache_redis_username and self.cache_redis_password:
            auth_part = f"{self.cache_redis_username}:{self.cache_redis_password}@"
        elif self.cache_redis_password:
            auth_part = f":{self.cache_redis_password}@"

        # Build base URL
        self.cache_redis_url = (
            f"{scheme}://{auth_part}{self.cache_redis_host}:{self.cache_redis_port}/"
            f"{self.cache_redis_db}"
        )

        # Add SSL parameters if needed
        if self.cache_redis_ssl:
            ssl_params = []
            if self.cache_redis_ssl_cert_reqs != "required":
                ssl_params.append(f"ssl_cert_reqs={self.cache_redis_ssl_cert_reqs}")

            if ssl_params:
                self.cache_redis_url += "?" + "&".join(ssl_params)

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
            errors.append(
                "Celery backend database configuration is required for result backend"
            )

        # Cache Redis validation
        if self.cache_redis_enabled:
            if not self.cache_redis_host:
                errors.append("CACHE_REDIS_HOST is required when cache is enabled")
            if self.cache_redis_port <= 0:
                errors.append("CACHE_REDIS_PORT must be positive")
            if self.cache_redis_db < 0:
                errors.append("CACHE_REDIS_DB must be non-negative")

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
            # Worker stability (useful for all workers)
            "worker_pool_restarts": os.getenv(
                "CELERY_WORKER_POOL_RESTARTS", "true"
            ).lower()
            == "true",
            "broker_connection_retry_on_startup": os.getenv(
                "CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP", "true"
            ).lower()
            == "true",
            "worker_send_task_events": True,
            "task_send_sent_event": True,
            "worker_log_format": "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
            "worker_task_log_format": "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
        }

    def get_coordinated_timeouts(self) -> dict[str, int]:
        """Calculate coordinated timeouts to prevent timeout mismatches between workflow steps.

        This ensures that if file processing takes a long time, the callback still has
        adequate time to complete. Prevents the issue where callback times out because
        it only gets its base timeout regardless of how long file processing took.

        Supports backward compatibility mode for gradual migration from old backend workers.

        Returns:
            dict: Coordinated timeout values for workflow steps
        """
        if not self.enable_coordinated_timeouts:
            # BACKWARD COMPATIBILITY MODE: Use individual timeout values like before
            # This allows gradual migration from old @backend/ workers to new @workers/
            return {
                "workflow_total": self.workflow_total_timeout,
                "file_processing": self.file_processing_timeout,
                "file_processing_soft": self.file_processing_soft_timeout,
                "callback": self.callback_timeout,
                "callback_soft": self.callback_soft_timeout,
            }

        # NEW COORDINATED MODE: Calculate coordinated timeouts
        # File processing gets 85%, callback gets 15%
        # This ensures callback always has adequate time after file processing completes
        file_timeout = int(self.workflow_total_timeout * 0.85)  # 85% for processing
        callback_timeout = max(
            int(self.workflow_total_timeout * 0.15),  # 15% for callback
            self.callback_min_timeout,  # But never less than minimum (5 minutes default)
        )

        return {
            "workflow_total": self.workflow_total_timeout,
            "file_processing": file_timeout,
            "file_processing_soft": int(file_timeout * 0.9),  # 90% of hard limit
            "callback": callback_timeout,
            "callback_soft": int(callback_timeout * 0.9),  # 90% of hard limit
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
            "celery_backend_db_password",
            "cache_redis_password",
            "cache_redis_url",
        ]
        for field_name in sensitive_fields:
            if field_name in safe_dict and safe_dict[field_name]:
                safe_dict[field_name] = "*" * 8

        return f"WorkerConfig({safe_dict})"

    def get_cache_redis_config(self) -> dict[str, Any]:
        """Get Redis cache-specific configuration for cache manager.

        Returns:
            Dictionary with Redis cache configuration
        """
        if not self.cache_redis_enabled:
            return {"enabled": False}

        config = {
            "enabled": True,
            "host": self.cache_redis_host,
            "port": self.cache_redis_port,
            "db": self.cache_redis_db,
            "url": self.cache_redis_url,
            "ssl": self.cache_redis_ssl,
        }

        # Add authentication if configured
        if self.cache_redis_password:
            config["password"] = self.cache_redis_password
        if self.cache_redis_username:
            config["username"] = self.cache_redis_username

        return config
