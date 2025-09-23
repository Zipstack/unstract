"""Task result and configuration models for the task abstraction layer."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class TaskResult:
    """Standardized result format for task execution across all backends.

    This model provides a unified way to represent task execution results
    regardless of which backend (Celery, Hatchet, Temporal) executed the task.
    """

    task_id: str
    task_name: str
    status: str  # pending, running, completed, failed
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def is_pending(self) -> bool:
        """Check if task is pending execution."""
        return self.status == "pending"

    @property
    def is_running(self) -> bool:
        """Check if task is currently running."""
        return self.status == "running"

    @property
    def is_completed(self) -> bool:
        """Check if task completed successfully."""
        return self.status == "completed"

    @property
    def is_failed(self) -> bool:
        """Check if task execution failed."""
        return self.status == "failed"

    @property
    def duration(self) -> Optional[float]:
        """Get task execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class BackendConfig:
    """Backend-specific configuration object.

    Contains the configuration needed to connect to and use a specific
    task backend (Celery, Hatchet, or Temporal).

    Note: Resilience features (retries, DLQ, persistence) should be
    configured in the backend's native configuration, not here.
    """

    backend_type: str  # celery, hatchet, temporal
    connection_params: Dict[str, Any]
    worker_config: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize worker_config if not provided."""
        if self.worker_config is None:
            self.worker_config = {}

    def validate(self) -> bool:
        """Validate configuration for the specified backend type."""
        if self.backend_type not in ["celery", "hatchet", "temporal"]:
            return False

        # Backend-specific validation
        if self.backend_type == "celery":
            required = ["broker_url"]
        elif self.backend_type == "hatchet":
            required = ["token", "server_url"]
        elif self.backend_type == "temporal":
            required = ["host", "port", "namespace", "task_queue"]
        else:
            return False

        return all(param in self.connection_params for param in required)