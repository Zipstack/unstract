"""Method Enumerations

Worker-specific method enums for notifications and processing.
"""

from enum import Enum


class NotificationMethod(str, Enum):
    """Notification delivery methods."""

    WEBHOOK = "webhook"
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"

    def __str__(self):
        """Return enum value for notification routing."""
        return self.value


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __str__(self):
        return self.value


class ConnectionType(str, Enum):
    """API connection types."""

    HTTP = "HTTP"
    HTTPS = "HTTPS"
    WEBSOCKET = "WEBSOCKET"

    def __str__(self):
        return self.value


class EndpointType(str, Enum):
    """API endpoint types."""

    REST = "REST"
    GRAPHQL = "GRAPHQL"
    WEBHOOK = "WEBHOOK"

    def __str__(self):
        return self.value


class FileOperationType(str, Enum):
    """File operation types."""

    READ = "READ"
    WRITE = "WRITE"
    DELETE = "DELETE"
    COPY = "COPY"
    MOVE = "MOVE"

    def __str__(self):
        return self.value


class FileDestinationType(str, Enum):
    """File destination types for workflow processing."""

    DESTINATION = "destination"
    MANUALREVIEW = "MANUALREVIEW"  # Backend uses this exact format

    def __str__(self):
        return self.value


class HTTPMethod(str, Enum):
    """HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

    def __str__(self):
        return self.value


class LogLevel(str, Enum):
    """Logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __str__(self):
        return self.value


class NotificationPlatform(str, Enum):
    """Notification platforms."""

    SLACK = "SLACK"
    DISCORD = "DISCORD"
    TEAMS = "TEAMS"
    EMAIL = "EMAIL"

    def __str__(self):
        return self.value


# AuthorizationType moved to unstract.core.notification_enums to avoid duplication
# Import from: from unstract.core.notification_enums import AuthorizationType
