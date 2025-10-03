"""Shared Enums for Worker Services

This module contains enum definitions used across worker services
to ensure type safety and prevent hardcoded string values.
"""

from enum import Enum

# Import unified ConnectionType from connectors package
from unstract.connectors import ConnectionType as UnifiedConnectionType

# AuthorizationType moved to unstract.core.notification_enums to avoid duplication
# Import from: from unstract.core.notification_enums import AuthorizationType


# Re-export for backward compatibility
ConnectionType = UnifiedConnectionType


class EndpointType(Enum):
    """Endpoint types for workflow configuration."""

    SOURCE = "SOURCE"
    DESTINATION = "DESTINATION"

    def __str__(self):
        return self.value


class HTTPMethod(Enum):
    """HTTP methods for API requests."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

    def __str__(self):
        return self.value


class CircuitBreakerState(Enum):
    """Circuit breaker states for resilience patterns."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __str__(self):
        return self.value


class LogLevel(Enum):
    """Log levels for structured logging."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __str__(self):
        return self.value


class TaskStatus(Enum):
    """Task status for asynchronous operations."""

    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"
    REVOKED = "REVOKED"

    def __str__(self):
        return self.value


class FileOperationType(Enum):
    """File operation types for file processing."""

    UPLOAD = "upload"
    DOWNLOAD = "download"
    DELETE = "delete"
    MOVE = "move"
    COPY = "copy"
    LIST = "list"

    def __str__(self):
        return self.value


class ToolOutputType(Enum):
    """Tool output types for processing results."""

    JSON = "JSON"
    TXT = "TXT"
    CSV = "CSV"
    XML = "XML"

    def __str__(self):
        return self.value


# Note: ExecutionStatus is imported from unstract.core.data_models to maintain consistency

# PipelineType moved to status_enums.py to avoid duplication
# Import from: from shared.enums import PipelineType


class NotificationPlatform(Enum):
    """Notification platforms for webhook delivery."""

    WEBHOOK = "webhook"
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"

    def __str__(self):
        return self.value


class BatchOperationType(Enum):
    """Batch operation types for bulk processing."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    STATUS_UPDATE = "status_update"

    def __str__(self):
        return self.value


# FileDestinationType moved to method_enums.py to avoid duplication
# Import from: from shared.enums import FileDestinationType


class FileHistoryStatus(Enum):
    """File history status types."""

    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    PARTIAL = "PARTIAL"

    def __str__(self):
        return self.value


# Legacy compatibility mappings
LEGACY_STATUS_MAPPING = {
    "INPROGRESS": "EXECUTING",
    "FAILED": "ERROR",
    "CANCELED": "STOPPED",
}

LEGACY_CONNECTION_TYPES = {
    "APPDEPLOYMENT": "API",
    "FILESYSTEM": "FILESYSTEM",
    "DATABASE": "DATABASE",
    "API": "API",
}
