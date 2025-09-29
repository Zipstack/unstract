"""Task abstraction layer - SQLAlchemy for task queues.

This package provides a unified interface for task execution across
multiple backends (Celery, Hatchet, Temporal), enabling backend
switching through configuration without code changes.

Basic usage:
    from task_abstraction import get_backend

    # Get backend from environment
    backend = get_backend("celery")

    # Register tasks
    @backend.register_task
    def add(x, y):
        return x + y

    # Submit tasks
    task_id = backend.submit("add", 2, 3)

    # Get results
    result = backend.get_result(task_id)
    if result.is_completed:
        print(result.result)  # 5
"""

from .base import TaskBackend
from .models import TaskResult, BackendConfig
from .factory import get_backend, create_backend, get_available_backends
from .config import (
    load_config_from_file,
    load_config_from_env,
    get_default_config
)
from .workflow import (
    workflow,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowExecutor,
    register_workflow
)
from .tasks import TASK_REGISTRY

__all__ = [
    # Core interface
    "TaskBackend",

    # Models
    "TaskResult",
    "BackendConfig",

    # Factory functions
    "get_backend",
    "create_backend",
    "get_available_backends",

    # Configuration
    "load_config_from_file",
    "load_config_from_env",
    "get_default_config",

    # Workflow support
    "workflow",
    "WorkflowDefinition",
    "WorkflowStep",
    "WorkflowExecutor",
    "register_workflow",

    # Task definitions
    "TASK_REGISTRY",
]

__version__ = "0.2.0"