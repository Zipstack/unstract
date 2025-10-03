"""Task Context and Error Models

Dataclasses for task execution context and error handling.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Import worker enums
from ..enums import TaskName

logger = logging.getLogger(__name__)


@dataclass
class TaskExecutionContext:
    """Execution context for worker tasks."""

    task_id: str
    task_name: TaskName
    organization_id: str
    execution_id: str | None = None
    workflow_id: str | None = None
    pipeline_id: str | None = None
    user_id: str | None = None
    correlation_id: str | None = None
    retry_count: int = 0
    started_at: datetime | None = None

    def __post_init__(self):
        """Set started_at if not provided."""
        if self.started_at is None:
            self.started_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging and tracing."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name.value,
            "organization_id": self.organization_id,
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "pipeline_id": self.pipeline_id,
            "retry_count": self.retry_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }

    def get_log_context(self) -> dict[str, Any]:
        """Get context suitable for structured logging."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name.value,
            "organization_id": self.organization_id,
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "pipeline_id": self.pipeline_id,
            "retry_count": self.retry_count,
        }


@dataclass
class TaskError:
    """Structured error information for task failures."""

    task_id: str
    task_name: TaskName
    error_type: str
    error_message: str
    traceback: str | None = None
    retry_count: int = 0
    occurred_at: datetime | None = None

    def __post_init__(self):
        """Set occurred_at if not provided."""
        if self.occurred_at is None:
            self.occurred_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for error reporting."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name.value,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "traceback": self.traceback,
            "retry_count": self.retry_count,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }

    @classmethod
    def from_exception(
        cls, task_id: str, task_name: TaskName, exception: Exception, retry_count: int = 0
    ) -> "TaskError":
        """Create from Python exception."""
        import traceback as tb

        return cls(
            task_id=task_id,
            task_name=task_name,
            error_type=type(exception).__name__,
            error_message=str(exception),
            traceback=tb.format_exc(),
            retry_count=retry_count,
        )


@dataclass
class TaskPerformanceMetrics:
    """Performance metrics for task execution monitoring."""

    task_name: str
    execution_time: float
    memory_usage: float | None = None
    cpu_usage: float | None = None
    error_count: int = 0
    retry_count: int = 0
    timestamp: datetime | None = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for metrics collection."""
        return {
            "task_name": self.task_name,
            "execution_time": self.execution_time,
            "memory_usage": self.memory_usage,
            "cpu_usage": self.cpu_usage,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class WorkerHealthMetrics:
    """Health metrics for worker instances."""

    worker_name: str
    worker_version: str
    uptime: float
    active_tasks: int
    completed_tasks: int
    failed_tasks: int
    memory_usage: float | None = None
    cpu_usage: float | None = None
    last_heartbeat: datetime | None = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.last_heartbeat is None:
            self.last_heartbeat = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for health monitoring."""
        return {
            "worker_name": self.worker_name,
            "worker_version": self.worker_version,
            "uptime": self.uptime,
            "active_tasks": self.active_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "memory_usage": self.memory_usage,
            "cpu_usage": self.cpu_usage,
            "last_heartbeat": self.last_heartbeat.isoformat()
            if self.last_heartbeat
            else None,
            "success_rate": self.success_rate,
        }

    @property
    def success_rate(self) -> float:
        """Calculate task success rate."""
        total_tasks = self.completed_tasks + self.failed_tasks
        if total_tasks == 0:
            return 100.0
        return (self.completed_tasks / total_tasks) * 100
