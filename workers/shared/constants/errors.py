"""Error Message Constants

Standardized error messages for workers.
"""


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
