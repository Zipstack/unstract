"""Executor Worker

Celery worker for the pluggable executor system.
Routes execute_extraction tasks to registered executors.
"""

import logging
import os

from queue_backend import worker_task
from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.EXECUTOR)
app, config = WorkerBuilder.build_celery_app(WorkerType.EXECUTOR)

# Suppress Celery trace logging of task return values.
# The trace logger prints the full result dict on task success, which
# can contain sensitive customer data (extracted text, summaries, etc.).
logging.getLogger("celery.app.trace").setLevel(logging.WARNING)


def check_executor_health():
    """Custom health check for executor worker."""
    from shared.infrastructure.monitoring.health import (
        HealthCheckResult,
        HealthStatus,
    )

    try:
        from unstract.sdk1.execution.registry import (
            ExecutorRegistry,
        )

        executors = ExecutorRegistry.list_executors()

        return HealthCheckResult(
            name="executor_health",
            status=HealthStatus.HEALTHY,
            message="Executor worker is healthy",
            details={
                "worker_type": "executor",
                "registered_executors": executors,
                "executor_count": len(executors),
                "queues": os.environ.get(
                    "CELERY_QUEUES_EXECUTOR", "celery_executor_legacy"
                ).split(","),
            },
        )

    except Exception as e:
        return HealthCheckResult(
            name="executor_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check
WorkerRegistry.register_health_check(
    WorkerType.EXECUTOR,
    "executor_health",
    check_executor_health,
)


@worker_task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "executor",
        "task_id": self.request.id,
        "worker_name": (config.worker_name if config else "executor-worker"),
    }


# Import tasks so shared_task definitions bind to this app.
import executor.tasks  # noqa: E402, F401
from executor.executors import register_all  # noqa: E402

# Populate ExecutorRegistry. Explicit because importing the package no longer
# registers as a side effect — that made every consumer of any submodule pay
# for the whole adapter stack. Idempotent, so executor/tasks.py calling it too
# is harmless.
register_all()
