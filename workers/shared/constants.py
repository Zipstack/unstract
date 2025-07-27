"""Worker-specific constants without Django dependencies.
This provides the essential constants needed by workers.
"""

import os


class FileProcessingConstants:
    """Constants for file processing operations."""

    # File chunk size for reading/writing (default 4MB like backend)
    # Backend uses: READ_CHUNK_SIZE = 4194304
    READ_CHUNK_SIZE = int(os.getenv("FILE_READ_CHUNK_SIZE", "4194304"))

    # Log preview size for truncating file content in logs (default 500 bytes like backend)
    # Backend uses: chunk[:500].decode("utf-8", errors="replace") + "...(truncated)"
    LOG_PREVIEW_SIZE = int(os.getenv("FILE_LOG_PREVIEW_SIZE", "500"))

    # File processing timeout in seconds
    PROCESSING_TIMEOUT = int(os.getenv("FILE_PROCESSING_TIMEOUT", "300"))

    # Optional: Maximum file size in MB for validation
    MAX_FILE_SIZE_MB = int(os.getenv("FILE_MAX_SIZE_MB", "100"))

    @classmethod
    def get_chunk_size(cls) -> int:
        """Get the configured chunk size for file operations."""
        return cls.READ_CHUNK_SIZE

    @classmethod
    def get_log_preview_size(cls) -> int:
        """Get the configured log preview size."""
        return cls.LOG_PREVIEW_SIZE

    @classmethod
    def get_max_file_size_bytes(cls) -> int:
        """Get the maximum file size in bytes."""
        return cls.MAX_FILE_SIZE_MB * 1024 * 1024


class WorkerConstants:
    """General worker operation constants."""

    # Default retry attempts for worker operations
    DEFAULT_RETRY_ATTEMPTS = int(os.getenv("WORKER_DEFAULT_RETRY_ATTEMPTS", "3"))

    # Default timeout for API calls
    API_TIMEOUT = int(os.getenv("WORKER_API_TIMEOUT", "30"))

    # Health check interval
    HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))


class Account:
    CREATED_BY = "created_by"
    MODIFIED_BY = "modified_by"
    ORGANIZATION_ID = "organization_id"


class Common:
    METADATA = "metadata"


# ExecutionStatus is now imported from shared data models above
# This ensures consistency between backend and workers


class FileExecutionStage:
    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class FileExecutionStageStatus:
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
