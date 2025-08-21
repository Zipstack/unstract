class LogFieldName:
    EXECUTION_ID = "execution_id"
    ORGANIZATION_ID = "organization_id"
    TIMESTAMP = "timestamp"
    TYPE = "type"
    DATA = "data"
    EVENT_TIME = "event_time"
    FILE_EXECUTION_ID = "file_execution_id"
    TOOL_TERMINATION_MARKER = "TOOL_EXECUTION_COMPLETE"


class LogEventArgument:
    EVENT = "event"
    MESSAGE = "message"
    USER_SESSION_ID = "user_session_id"


class LogProcessingTask:
    TASK_NAME = "logs_consumer"
    QUEUE_NAME = "celery_log_task_queue"


class FileProcessingConstants:
    """Constants for file processing operations."""

    # File chunk size for reading/writing (4MB default)
    READ_CHUNK_SIZE = 4194304  # 4MB chunks for file reading

    # Log preview size for truncating file content in logs
    LOG_PREVIEW_SIZE = 500  # 500 bytes for log preview

    # File processing timeout in seconds
    DEFAULT_PROCESSING_TIMEOUT = 300  # 5 minutes

    # Maximum file size in bytes for validation
    MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB

    @classmethod
    def get_chunk_size(cls) -> int:
        """Get the configured chunk size for file operations."""
        return cls.READ_CHUNK_SIZE

    @classmethod
    def get_log_preview_size(cls) -> int:
        """Get the configured log preview size."""
        return cls.LOG_PREVIEW_SIZE


class WorkerConstants:
    """General worker operation constants."""

    # Default retry attempts for worker operations
    DEFAULT_RETRY_ATTEMPTS = 3

    # Default timeout for API calls
    API_TIMEOUT = 30

    # Health check interval
    HEALTH_CHECK_INTERVAL = 30
