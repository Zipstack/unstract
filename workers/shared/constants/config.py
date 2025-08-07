"""Worker Configuration Constants

Default configuration values for workers.
"""


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
