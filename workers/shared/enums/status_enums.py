"""Status Enumerations

Worker-specific status enums for tasks, pipelines, and webhooks.
"""

from enum import Enum


class WorkerTaskStatus(str, Enum):
    """Task execution status for workers."""

    PENDING = "PENDING"
    STARTED = "STARTED"
    RETRY = "RETRY"
    FAILURE = "FAILURE"
    SUCCESS = "SUCCESS"
    REVOKED = "REVOKED"

    def __str__(self):
        """Return enum value for Celery status comparison."""
        return self.value


class PipelineStatus(str, Enum):
    """Pipeline execution status mapping."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    INPROGRESS = "INPROGRESS"
    YET_TO_START = "YET_TO_START"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"

    def __str__(self):
        """Return enum value for API updates."""
        return self.value


class WebhookStatus(str, Enum):
    """Webhook delivery status."""

    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRY = "retry"

    def __str__(self):
        """Return enum value for webhook tracking."""
        return self.value


class TaskStatus(str, Enum):
    """Generic task status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SUCCESS = "success"  # Alias for completed
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

    def __str__(self):
        return self.value


class ToolOutputType(str, Enum):
    """Tool output types."""

    TEXT = "text"
    JSON = "json"
    XML = "xml"
    BINARY = "binary"
    IMAGE = "image"

    def __str__(self):
        return self.value
