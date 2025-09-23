"""Task Backend Worker Service.

This service uses the unstract-task-abstraction library to initialize and manage
backend-specific workers (Celery, Hatchet, Temporal).

Unlike HTTP services, this is a worker process that:
- Connects to the configured backend (Redis for Celery, Hatchet server, Temporal server)
- Registers workflows using the task-abstraction library
- Runs appropriate worker processes based on backend type

Usage:
    # Start worker (auto-detects backend from env)
    task-backend-worker

    # Start specific backend worker
    task-backend-worker --backend=celery
    task-backend-worker --backend=hatchet
    task-backend-worker --backend=temporal
"""

__version__ = "0.1.0"

from .config import TaskBackendConfig, get_task_backend_config
from .worker import TaskBackendWorker
from .tasks import TASK_REGISTRY

__all__ = ["TaskBackendConfig", "get_task_backend_config", "TaskBackendWorker", "TASK_REGISTRY"]