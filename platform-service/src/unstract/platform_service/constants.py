class FeatureFlag:
    """Temporary feature flags."""

    # For enabling remote storage feature
    REMOTE_FILE_STORAGE = "remote_file_storage"


class DBTable:
    """Database tables."""

    ORGANIZATION = "organization"
    ADAPTER_INSTANCE = "adapter_instance"
    PROMPT_STUDIO_REGISTRY = "prompt_studio_registry"
    PLATFORM_KEY = "platform_key"
    TOKEN_USAGE = "usage"
    PAGE_USAGE = "page_usage"


class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
