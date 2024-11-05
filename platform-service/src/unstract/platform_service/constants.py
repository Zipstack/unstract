class FeatureFlag:
    """Temporary feature flags."""

    pass


class DBTable:
    """Database tables."""

    PAGE_USAGE = "page_usage"


class DBTableV2:
    """Database tables."""

    ORGANIZATION = "organization"
    ADAPTER_INSTANCE = "adapter_instance"
    PROMPT_STUDIO_REGISTRY = "prompt_studio_registry"
    PLATFORM_KEY = "platform_key"
    TOKEN_USAGE = "usage"


class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
