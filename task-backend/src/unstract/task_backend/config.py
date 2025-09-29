"""Configuration for the task backend worker service."""

from typing import List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseWorkerConfig(BaseSettings):
    """Base configuration shared across all backends."""

    model_config = SettingsConfigDict(
        env_prefix="TASK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Worker Configuration
    backend_type: str = Field(default="celery", description="Backend type to use")
    worker_name: str = Field(default="", description="Worker instance name (auto-generated if empty)")
    worker_concurrency: int = Field(default=4, description="Worker concurrency level")

    # Monitoring Configuration
    log_level: str = Field(default="INFO", description="Global log level")
    structured_logging: bool = Field(default=True, description="Enable structured logging")

    # Health Check Configuration
    health_check_interval: int = Field(default=30, description="Health check interval in seconds")
    backend_health_timeout: int = Field(default=10, description="Backend health timeout in seconds")

    # Shutdown Configuration
    shutdown_timeout: int = Field(default=30, description="Graceful shutdown timeout in seconds")


class CeleryWorkerConfig(BaseWorkerConfig):
    """Configuration specific to Celery backend."""

    # Celery Configuration
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        description="Celery broker URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0",
        description="Celery result backend URL"
    )
    def get_backend_specific_config(self, queues: List[str] = None) -> dict:
        """Get Celery-specific configuration."""
        return {
            "broker_url": self.celery_broker_url,
            "result_backend": self.celery_result_backend,
            "queues": queues or ["celery"],  # Use provided queues or default
            "concurrency": self.worker_concurrency,
        }


class HatchetWorkerConfig(BaseWorkerConfig):
    """Configuration specific to Hatchet backend."""

    # Hatchet Configuration
    hatchet_token: str = Field(
        description="Hatchet client token (required)"
    )
    hatchet_server_url: str = Field(
        default="https://app.hatchet.run",
        description="Hatchet server URL"
    )
    hatchet_tls_strategy: str = Field(
        default="tls",
        description="Hatchet TLS strategy"
    )
    hatchet_worker_name: str = Field(
        default="task-worker",
        description="Hatchet worker name"
    )

    def get_backend_specific_config(self, queues: List[str] = None) -> dict:
        """Get Hatchet-specific configuration."""
        return {
            "token": self.hatchet_token,
            "server_url": self.hatchet_server_url,
            "tls_strategy": self.hatchet_tls_strategy,
            "worker_name": self.hatchet_worker_name,
            "workflows": queues or ["default"],  # Map queues to workflows
        }


class TemporalWorkerConfig(BaseWorkerConfig):
    """Configuration specific to Temporal backend."""

    # Temporal Configuration
    temporal_host: str = Field(default="localhost", description="Temporal host")
    temporal_port: int = Field(default=7233, description="Temporal port")
    temporal_namespace: str = Field(default="default", description="Temporal namespace")
    temporal_task_queue: str = Field(default="task-queue", description="Temporal task queue")
    temporal_worker_identity: str = Field(
        default="task-worker-01",
        description="Temporal worker identity"
    )

    def get_backend_specific_config(self, queues: List[str] = None) -> dict:
        """Get Temporal-specific configuration."""
        return {
            "host": self.temporal_host,
            "port": self.temporal_port,
            "namespace": self.temporal_namespace,
            "task_queues": queues or ["default"],  # Map queues to task queues
            "worker_identity": self.temporal_worker_identity,
        }


# Type alias for all worker config types
TaskBackendConfig = Union[CeleryWorkerConfig, HatchetWorkerConfig, TemporalWorkerConfig]


def get_task_backend_config() -> TaskBackendConfig:
    """Get task backend configuration instance for the specified backend type."""
    # First load base config to determine backend type
    base_config = BaseWorkerConfig()
    backend_type = base_config.backend_type

    # Return backend-specific config class
    if backend_type == "celery":
        return CeleryWorkerConfig()
    elif backend_type == "hatchet":
        return HatchetWorkerConfig()
    elif backend_type == "temporal":
        return TemporalWorkerConfig()
    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")


def get_backend_config_for_type(backend_type: str) -> TaskBackendConfig:
    """Get configuration for a specific backend type."""
    if backend_type == "celery":
        return CeleryWorkerConfig()
    elif backend_type == "hatchet":
        return HatchetWorkerConfig()
    elif backend_type == "temporal":
        return TemporalWorkerConfig()
    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")