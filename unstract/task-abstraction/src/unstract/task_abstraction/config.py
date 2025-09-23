"""Configuration management for task backends."""

import os
from typing import Dict, Any, Optional
from .models import BackendConfig

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


def load_config_from_file(config_path: str) -> BackendConfig:
    """Load backend configuration from a YAML file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        BackendConfig instance

    Example YAML structure:
        backend: celery
        celery:
          broker_url: redis://localhost:6379/0
          result_backend: redis://localhost:6379/0
        worker:
          concurrency: 4
          max_tasks_per_child: 100
    """
    if not YAML_AVAILABLE:
        raise ImportError("PyYAML is not installed. Install with: pip install pyyaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        config_data = yaml.safe_load(f)

    backend_type = config_data.get('backend')
    if not backend_type:
        raise ValueError("Backend type must be specified in configuration")

    # Get backend-specific connection parameters
    connection_params = config_data.get(backend_type, {})
    worker_config = config_data.get('worker', {})

    config = BackendConfig(
        backend_type=backend_type,
        connection_params=connection_params,
        worker_config=worker_config
    )

    if not config.validate():
        raise ValueError(f"Invalid configuration for backend type: {backend_type}")

    return config


def load_config_from_env(backend_type: str) -> BackendConfig:
    """Load backend configuration from environment variables.

    Args:
        backend_type: Backend type (celery, hatchet, temporal)

    Returns:
        BackendConfig instance

    Environment variables:
        Celery:
            CELERY_BROKER_URL
            CELERY_RESULT_BACKEND

        Hatchet:
            HATCHET_TOKEN
            HATCHET_SERVER_URL

        Temporal:
            TEMPORAL_HOST
            TEMPORAL_PORT
            TEMPORAL_NAMESPACE
            TEMPORAL_TASK_QUEUE
    """
    connection_params = {}
    worker_config = {}

    if backend_type == "celery":
        connection_params = {
            "broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
            "result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
        }
        worker_config = {
            "concurrency": int(os.getenv("CELERY_WORKER_CONCURRENCY", "4")),
            "max_tasks_per_child": int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "100")),
        }

    elif backend_type == "hatchet":
        connection_params = {
            "token": os.getenv("HATCHET_TOKEN"),
            "server_url": os.getenv("HATCHET_SERVER_URL", "https://app.hatchet.run"),
        }
        worker_config = {
            "worker_name": os.getenv("HATCHET_WORKER_NAME", "default-worker"),
            "max_runs": int(os.getenv("HATCHET_MAX_RUNS", "100")),
        }

    elif backend_type == "temporal":
        connection_params = {
            "host": os.getenv("TEMPORAL_HOST", "localhost"),
            "port": int(os.getenv("TEMPORAL_PORT", "7233")),
            "namespace": os.getenv("TEMPORAL_NAMESPACE", "default"),
            "task_queue": os.getenv("TEMPORAL_TASK_QUEUE", "default-queue"),
        }
        worker_config = {
            "max_concurrent_activities": int(os.getenv("TEMPORAL_MAX_ACTIVITIES", "100")),
            "max_concurrent_workflow_tasks": int(os.getenv("TEMPORAL_MAX_WORKFLOWS", "100")),
        }

    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")

    config = BackendConfig(
        backend_type=backend_type,
        connection_params=connection_params,
        worker_config=worker_config
    )

    if not config.validate():
        raise ValueError(f"Invalid environment configuration for backend: {backend_type}")

    return config


def get_default_config(backend_type: str) -> BackendConfig:
    """Get default configuration for a backend type.

    Args:
        backend_type: Backend type (celery, hatchet, temporal)

    Returns:
        BackendConfig with default values
    """
    if backend_type == "celery":
        return BackendConfig(
            backend_type="celery",
            connection_params={
                "broker_url": "redis://localhost:6379/0",
                "result_backend": "redis://localhost:6379/0",
            },
            worker_config={
                "concurrency": 4,
                "max_tasks_per_child": 100,
            }
        )

    elif backend_type == "hatchet":
        return BackendConfig(
            backend_type="hatchet",
            connection_params={
                "token": "your-hatchet-token",
                "server_url": "https://app.hatchet.run",
            },
            worker_config={
                "worker_name": "default-worker",
                "max_runs": 100,
            }
        )

    elif backend_type == "temporal":
        return BackendConfig(
            backend_type="temporal",
            connection_params={
                "host": "localhost",
                "port": 7233,
                "namespace": "default",
                "task_queue": "default-queue",
            },
            worker_config={
                "max_concurrent_activities": 100,
                "max_concurrent_workflow_tasks": 100,
            }
        )

    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")