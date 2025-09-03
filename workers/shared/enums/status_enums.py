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

    @classmethod
    def is_completion_status(cls, status: str) -> bool:
        """Check if a pipeline status represents a completion state.

        Completion states are final states that should trigger last_run_time updates.

        Args:
            status: Status string to check

        Returns:
            True if status is a completion state
        """
        # Pipeline completion states - these are final states
        completion_statuses = {
            cls.SUCCESS.value,
            cls.FAILURE.value,
            cls.PARTIAL_SUCCESS.value,  # Also a completion state with mixed results
        }

        # Check if the status (uppercased) matches any completion status
        status_upper = status.upper()
        return status_upper in completion_statuses


class PipelineType(str, Enum):
    """Pipeline types for workflows."""

    ETL = "ETL"
    TASK = "TASK"
    API = "API"
    APP = "APP"
    DEFAULT = "DEFAULT"

    def __str__(self):
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

    @classmethod
    def is_completion_status(cls, status: str) -> bool:
        """Check if a status represents a completion state.

        Args:
            status: Status string to check

        Returns:
            True if status is a completion state
        """
        completion_statuses = {
            cls.COMPLETED.value.upper(),
            cls.SUCCESS.value.upper(),
            cls.FAILED.value.upper(),
            cls.CANCELLED.value.upper(),
        }
        return status.upper() in completion_statuses


class ToolOutputType(str, Enum):
    """Tool output types."""

    TEXT = "text"
    JSON = "json"
    XML = "xml"
    BINARY = "binary"
    IMAGE = "image"

    def __str__(self):
        return self.value
