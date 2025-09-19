"""Security Configuration Constants

Security and validation configuration.
"""


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
