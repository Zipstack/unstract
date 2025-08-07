"""Worker Constants and Configuration

This module contains constants, configuration values, and utility functions
used across all worker implementations to ensure consistency.
"""


# API Endpoint Constants
class APIEndpoints:
    """Internal API endpoint paths."""

    # Workflow execution endpoints
    WORKFLOW_EXECUTION_STATUS = "/internal/workflow-execution/{execution_id}/status/"
    WORKFLOW_EXECUTION_DATA = "/internal/workflow-execution/{execution_id}/"
    WORKFLOW_FILE_EXECUTION_CREATE = "/internal/workflow-file-execution/create/"
    WORKFLOW_FILE_EXECUTION_STATUS = (
        "/internal/workflow-file-execution/{file_execution_id}/status/"
    )

    # Pipeline endpoints
    PIPELINE_STATUS = "/internal/pipeline/{pipeline_id}/status/"
    PIPELINE_LAST_RUN = "/internal/pipeline/{pipeline_id}/last-run/"

    # File history endpoints
    FILE_HISTORY_CREATE = "/internal/file-history/create/"
    FILE_HISTORY_CHECK_BATCH = "/internal/file-history/check-batch/"
    FILE_HISTORY_BY_WORKFLOW = "/internal/file-history/workflow/{workflow_id}/"

    # Workflow definition endpoints
    WORKFLOW_DEFINITION = "/internal/workflow/{workflow_id}/"
    WORKFLOW_SOURCE_CONFIG = "/internal/workflow/{workflow_id}/source-config/"
    WORKFLOW_DESTINATION_CONFIG = "/internal/workflow/{workflow_id}/destination-config/"

    # Notification endpoints
    WEBHOOK_SEND = "/internal/webhook/send/"
    NOTIFICATION_SEND = "/internal/notification/send/"

    # Health and monitoring endpoints
    WORKER_HEALTH = "/internal/worker/health/"
    WORKER_METRICS = "/internal/worker/metrics/"


# Default Configuration Values
class DefaultConfig:
    """Default configuration values for workers."""

    # Task timeouts (in seconds)
    DEFAULT_TASK_TIMEOUT = 300  # 5 minutes
    FILE_PROCESSING_TIMEOUT = 1800  # 30 minutes
    CALLBACK_TIMEOUT = 120  # 2 minutes
    WEBHOOK_TIMEOUT = 30  # 30 seconds

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


# Error Messages
class ErrorMessages:
    """Standardized error messages."""

    # Task execution errors
    TASK_TIMEOUT = "Task execution timed out after {timeout} seconds"
    TASK_RETRY_EXHAUSTED = "Task failed after {max_retries} retry attempts"
    TASK_INVALID_INPUT = "Task received invalid input: {details}"
    TASK_MISSING_CONTEXT = "Task execution context is missing or invalid"

    # File processing errors
    FILE_NOT_FOUND = "File not found: {file_path}"
    FILE_ACCESS_DENIED = "Access denied for file: {file_path}"
    FILE_SIZE_EXCEEDED = "File size {size}MB exceeds maximum limit of {max_size}MB"
    FILE_FORMAT_UNSUPPORTED = "Unsupported file format: {mime_type}"
    FILE_PROCESSING_FAILED = "Failed to process file {file_name}: {error}"

    # API communication errors
    API_CONNECTION_FAILED = "Failed to connect to internal API: {error}"
    API_AUTHENTICATION_FAILED = "API authentication failed: {error}"
    API_REQUEST_TIMEOUT = "API request timed out after {timeout} seconds"
    API_INVALID_RESPONSE = "Invalid API response format: {details}"
    API_SERVER_ERROR = "Internal API server error: {status_code} - {message}"

    # Configuration errors
    CONFIG_MISSING_REQUIRED = "Missing required configuration: {field}"
    CONFIG_INVALID_VALUE = "Invalid configuration value for {field}: {value}"
    CONFIG_VALIDATION_FAILED = "Configuration validation failed: {errors}"

    # Worker errors
    WORKER_INITIALIZATION_FAILED = "Worker initialization failed: {error}"
    WORKER_HEALTH_CHECK_FAILED = "Worker health check failed: {error}"
    WORKER_RESOURCE_EXHAUSTED = "Worker resources exhausted: {resource}"


# Log Messages and Levels
class LogMessages:
    """Standardized log messages."""

    # Task lifecycle
    TASK_STARTED = "Task {task_name} started with ID {task_id}"
    TASK_COMPLETED = "Task {task_name} completed successfully in {execution_time:.2f}s"
    TASK_FAILED = "Task {task_name} failed: {error}"
    TASK_RETRYING = "Task {task_name} retrying attempt {attempt}/{max_retries}"

    # File processing
    FILE_PROCESSING_STARTED = "Started processing file batch with {file_count} files"
    FILE_PROCESSING_COMPLETED = (
        "Completed file batch processing: {successful}/{total} files successful"
    )
    FILE_EXECUTION_CREATED = "Created file execution record for {file_name}"
    FILE_STATUS_UPDATED = "Updated file execution status to {status} for {file_name}"

    # Callback processing
    CALLBACK_TRIGGERED = (
        "Callback triggered for execution {execution_id} with {batch_count} batches"
    )
    CALLBACK_AGGREGATING = "Aggregating results from {batch_count} batch executions"
    CALLBACK_STATUS_UPDATE = "Updating execution status to {status} for {execution_id}"
    CALLBACK_COMPLETED = "Callback processing completed for execution {execution_id}"

    # Cache operations
    CACHE_HIT = "Cache hit for {cache_key}"
    CACHE_MISS = "Cache miss for {cache_key}"
    CACHE_SET = "Cached data for {cache_key} with TTL {ttl}s"
    CACHE_INVALIDATED = "Invalidated cache for {cache_key}"
    CACHE_CONNECTION_LOST = "Redis connection lost, clearing potentially stale cache"

    # Health and monitoring
    WORKER_STARTED = "Worker {worker_name} started with version {version}"
    WORKER_HEALTH_OK = "Worker health check passed"
    WORKER_HEALTH_DEGRADED = "Worker health check degraded: {issues}"
    METRICS_COLLECTED = "Performance metrics collected: {metrics}"


# Queue Configuration
class QueueConfig:
    """Queue routing and configuration."""

    # Queue routing rules
    TASK_ROUTES = {
        "send_webhook_notification": {"queue": "general"},
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
    }

    # Queue priorities (higher number = higher priority)
    QUEUE_PRIORITIES = {
        "callback": 9,  # Highest priority for completion callbacks
        "webhook": 8,  # High priority for notifications
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


# File Processing Constants
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


# Monitoring and Metrics Constants
class MonitoringConfig:
    """Monitoring and metrics configuration."""

    # Metric collection intervals
    TASK_METRICS_INTERVAL = 10  # 10 seconds
    WORKER_METRICS_INTERVAL = 30  # 30 seconds
    HEALTH_CHECK_INTERVAL = 60  # 1 minute

    # Performance thresholds
    TASK_SLOW_THRESHOLD = 30.0  # 30 seconds
    MEMORY_WARNING_THRESHOLD = 80  # 80% of max memory
    ERROR_RATE_WARNING_THRESHOLD = 5.0  # 5% error rate

    # Metric retention periods
    TASK_METRICS_RETENTION = 3600  # 1 hour
    WORKER_METRICS_RETENTION = 86400  # 24 hours
    ERROR_METRICS_RETENTION = 604800  # 7 days

    # Alert thresholds
    CONSECUTIVE_FAILURES_ALERT = 5
    HIGH_ERROR_RATE_ALERT = 10.0  # 10%
    MEMORY_CRITICAL_ALERT = 95  # 95%


# Cache Configuration
class CacheConfig:
    """Redis cache configuration and patterns."""

    # Cache key patterns
    EXECUTION_STATUS_PATTERN = "exec_status:{org_id}:{execution_id}"
    PIPELINE_STATUS_PATTERN = "pipeline_status:{org_id}:{pipeline_id}"
    BATCH_SUMMARY_PATTERN = "batch_summary:{org_id}:{execution_id}"
    CALLBACK_ATTEMPTS_PATTERN = "callback_attempts:{org_id}:{execution_id}"
    BACKOFF_ATTEMPTS_PATTERN = "backoff_attempts:{org_id}:{execution_id}:{operation}"
    CIRCUIT_BREAKER_PATTERN = "circuit_breaker:{service}:{operation}"

    # TTL values (in seconds)
    EXECUTION_STATUS_TTL = 60
    PIPELINE_STATUS_TTL = 120
    BATCH_SUMMARY_TTL = 90
    CALLBACK_ATTEMPTS_TTL = 3600  # 1 hour
    BACKOFF_ATTEMPTS_TTL = 1800  # 30 minutes
    CIRCUIT_BREAKER_TTL = 300  # 5 minutes

    # Cache validation settings
    MAX_CACHE_AGE = 300  # 5 minutes absolute max
    STALE_DATA_THRESHOLD = 120  # 2 minutes

    # Connection settings
    REDIS_SOCKET_TIMEOUT = 5
    REDIS_SOCKET_CONNECT_TIMEOUT = 5
    REDIS_HEALTH_CHECK_INTERVAL = 30


# Security and Validation Constants
class SecurityConfig:
    """Security and validation configuration."""

    # Input validation patterns
    VALID_UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    VALID_ORGANIZATION_ID_PATTERN = r"^[a-zA-Z0-9_-]+$"
    VALID_FILE_NAME_PATTERN = r'^[^<>:"/\\|?*\x00-\x1f]+$'

    # Maximum field lengths
    MAX_ERROR_MESSAGE_LENGTH = 2048
    MAX_TASK_NAME_LENGTH = 100
    MAX_FILE_NAME_LENGTH = 255
    MAX_FILE_PATH_LENGTH = 4096

    # Allowed characters
    SAFE_FILENAME_CHARS = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- "
    )

    # Security headers for API requests
    REQUIRED_HEADERS = [
        "Authorization",
        "Content-Type",
    ]

    # Rate limiting
    API_RATE_LIMIT_PER_MINUTE = 1000
    WEBHOOK_RATE_LIMIT_PER_MINUTE = 100


# Environment Variable Names
class EnvVars:
    """Environment variable names for configuration."""

    # Worker identification
    WORKER_NAME = "WORKER_NAME"
    WORKER_VERSION = "WORKER_VERSION"
    WORKER_INSTANCE_ID = "HOSTNAME"

    # Celery configuration
    CELERY_BROKER_BASE_URL = "CELERY_BROKER_BASE_URL"
    CELERY_BROKER_USER = "CELERY_BROKER_USER"
    CELERY_BROKER_PASS = "CELERY_BROKER_PASS"

    # Celery backend database
    CELERY_BACKEND_DB_HOST = "CELERY_BACKEND_DB_HOST"
    CELERY_BACKEND_DB_PORT = "CELERY_BACKEND_DB_PORT"
    CELERY_BACKEND_DB_NAME = "CELERY_BACKEND_DB_NAME"
    CELERY_BACKEND_DB_USER = "CELERY_BACKEND_DB_USER"
    CELERY_BACKEND_DB_PASSWORD = "CELERY_BACKEND_DB_PASSWORD"
    CELERY_BACKEND_DB_SCHEMA = "CELERY_BACKEND_DB_SCHEMA"

    # Redis cache configuration - these are env var names, not secrets
    CACHE_REDIS_ENABLED = "CACHE_REDIS_ENABLED"
    CACHE_REDIS_HOST = "CACHE_REDIS_HOST"
    CACHE_REDIS_PORT = "CACHE_REDIS_PORT"
    CACHE_REDIS_DB = "CACHE_REDIS_DB"
    CACHE_REDIS_PASSWORD = "CACHE_REDIS_PASSWORD"  # gitleaks:allow
    CACHE_REDIS_USERNAME = "CACHE_REDIS_USERNAME"
    CACHE_REDIS_SSL = "CACHE_REDIS_SSL"

    # Internal API configuration
    INTERNAL_API_BASE_URL = "INTERNAL_API_BASE_URL"
    DJANGO_APP_BACKEND_URL = "DJANGO_APP_BACKEND_URL"
    INTERNAL_SERVICE_API_KEY = "INTERNAL_SERVICE_API_KEY"

    # Performance settings
    MAX_CONCURRENT_TASKS = "MAX_CONCURRENT_TASKS"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    MAX_PARALLEL_FILE_BATCHES = "MAX_PARALLEL_FILE_BATCHES"

    # Monitoring settings
    ENABLE_METRICS = "ENABLE_METRICS"
    ENABLE_HEALTH_SERVER = "ENABLE_HEALTH_SERVER"
    METRICS_PORT = "METRICS_PORT"

    # Logging configuration
    LOG_LEVEL = "LOG_LEVEL"
    LOG_FORMAT = "LOG_FORMAT"
    LOG_FILE = "LOG_FILE"


# Helper Functions
def get_cache_key(pattern: str, **kwargs) -> str:
    """Generate cache key from pattern and parameters."""
    try:
        return pattern.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing parameter for cache key pattern {pattern}: {e}")


def validate_execution_id(execution_id: str) -> bool:
    """Validate execution ID format."""
    import re

    return bool(re.match(SecurityConfig.VALID_UUID_PATTERN, execution_id))


def validate_organization_id(org_id: str) -> bool:
    """Validate organization ID format."""
    import re

    return bool(re.match(SecurityConfig.VALID_ORGANIZATION_ID_PATTERN, org_id))


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    import os
    import re

    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    # Limit length
    if len(sanitized) > SecurityConfig.MAX_FILE_NAME_LENGTH:
        name, ext = os.path.splitext(sanitized)
        max_name_length = SecurityConfig.MAX_FILE_NAME_LENGTH - len(ext)
        sanitized = name[:max_name_length] + ext
    return sanitized


def get_task_timeout(task_name: str) -> int:
    """Get timeout for specific task type."""
    timeouts = {
        "process_file_batch": DefaultConfig.FILE_PROCESSING_TIMEOUT,
        "process_batch_callback": DefaultConfig.CALLBACK_TIMEOUT,
        "send_webhook_notification": DefaultConfig.WEBHOOK_TIMEOUT,
    }
    return timeouts.get(task_name, DefaultConfig.DEFAULT_TASK_TIMEOUT)


def get_task_max_retries(task_name: str) -> int:
    """Get max retries for specific task type."""
    retries = {
        "process_file_batch": DefaultConfig.FILE_PROCESSING_MAX_RETRIES,
        "process_batch_callback": DefaultConfig.CALLBACK_MAX_RETRIES,
        "send_webhook_notification": DefaultConfig.WEBHOOK_MAX_RETRIES,
    }
    return retries.get(task_name, DefaultConfig.DEFAULT_MAX_RETRIES)
