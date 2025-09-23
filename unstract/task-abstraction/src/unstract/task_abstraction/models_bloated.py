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


@dataclass
class PersistenceConfig:
    """Configuration for workflow state persistence across backends.

    Supports both native backend persistence and unified cross-backend storage.
    """

    use_native_persistence: bool = True
    """Use the backend's native persistence mechanism (Redis for Celery, PostgreSQL for Hatchet, etc.)"""

    unified_state_store: Optional[str] = None
    """Optional unified state store: 'redis', 'postgres', 'memory', or None for native only"""

    enable_cross_backend_compat: bool = False
    """Enable cross-backend workflow compatibility (requires unified_state_store)"""

    state_ttl_seconds: Optional[int] = None
    """TTL for workflow state in unified store (None = no expiration)"""

    connection_params: Optional[Dict[str, Any]] = None
    """Connection parameters for unified state store"""

    def __post_init__(self):
        """Validate persistence configuration."""
        if self.enable_cross_backend_compat and not self.unified_state_store:
            raise ValueError("Cross-backend compatibility requires unified_state_store")

        if self.connection_params is None:
            self.connection_params = {}

    @property
    def requires_unified_store(self) -> bool:
        """Check if configuration requires a unified state store."""
        return bool(self.unified_state_store) or self.enable_cross_backend_compat

    def validate(self) -> bool:
        """Validate persistence configuration."""
        if self.unified_state_store and self.unified_state_store not in ['redis', 'postgres', 'memory']:
            return False

        if self.enable_cross_backend_compat and not self.unified_state_store:
            return False

        # Validate connection params for unified stores
        if self.unified_state_store == 'redis':
            # Redis requires at least host
            return 'host' in self.connection_params
        elif self.unified_state_store == 'postgres':
            # PostgreSQL requires connection string or connection components
            return ('connection_string' in self.connection_params or
                   all(key in self.connection_params for key in ['host', 'database']))

        return True