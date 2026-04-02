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


class FilePatternConstants:
    """Constants for file pattern matching and translation."""

    # Display name to file pattern mappings
    # Maps UI-friendly display names to actual file matching patterns
    DISPLAY_NAME_TO_PATTERNS = {
        "pdf documents": ["*.pdf"],
        "word documents": ["*.doc", "*.docx"],
        "excel documents": ["*.xls", "*.xlsx"],
        "powerpoint documents": ["*.ppt", "*.pptx"],
        "text files": ["*.txt"],
        "image files": ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.tiff", "*.tif"],
        "csv files": ["*.csv"],
        "json files": ["*.json"],
        "xml files": ["*.xml"],
        "all files": ["*"],
        "office documents": ["*.doc", "*.docx", "*.xls", "*.xlsx", "*.ppt", "*.pptx"],
        "document files": ["*.pdf", "*.doc", "*.docx", "*.txt"],
        "spreadsheet files": ["*.xls", "*.xlsx", "*.csv"],
        "presentation files": ["*.ppt", "*.pptx"],
        "archive files": ["*.zip", "*.rar", "*.7z", "*.tar", "*.gz"],
        "video files": ["*.mp4", "*.avi", "*.mov", "*.wmv", "*.flv", "*.mkv"],
        "audio files": ["*.mp3", "*.wav", "*.flac", "*.aac", "*.ogg"],
    }

    # Common file extension categories for inference
    EXTENSION_CATEGORIES = {
        "pdf": ["*.pdf"],
        "doc": ["*.doc", "*.docx"],
        "excel": ["*.xls", "*.xlsx"],
        "image": ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.tiff", "*.tif"],
        "text": ["*.txt"],
        "csv": ["*.csv"],
        "json": ["*.json"],
        "xml": ["*.xml"],
        "office": ["*.doc", "*.docx", "*.xls", "*.xlsx", "*.ppt", "*.pptx"],
        "archive": ["*.zip", "*.rar", "*.7z", "*.tar", "*.gz"],
        "video": ["*.mp4", "*.avi", "*.mov", "*.wmv", "*.flv", "*.mkv"],
        "audio": ["*.mp3", "*.wav", "*.flac", "*.aac", "*.ogg"],
    }

    @classmethod
    def get_patterns_for_display_name(cls, display_name: str) -> list[str] | None:
        """Get file patterns for a given display name.

        Args:
            display_name: UI display name (e.g., "PDF documents")

        Returns:
            List of file patterns or None if not found
        """
        return cls.DISPLAY_NAME_TO_PATTERNS.get(display_name.strip().lower())

    @classmethod
    def infer_patterns_from_keyword(cls, keyword: str) -> list[str] | None:
        """Infer file patterns from a keyword.

        Args:
            keyword: Keyword to search for (e.g., "pdf", "excel")

        Returns:
            List of file patterns or None if not found
        """
        keyword_lower = keyword.strip().lower()

        for category, patterns in cls.EXTENSION_CATEGORIES.items():
            if category in keyword_lower:
                return patterns

        return None
