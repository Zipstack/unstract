"""Scheduler Worker

Celery worker for scheduled tasks and background processing.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.SCHEDULER)
app, config = WorkerBuilder.build_celery_app(WorkerType.SCHEDULER)


def check_scheduler_health():
    """Custom health check for scheduler worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.legacy.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="scheduler_health",
                status=HealthStatus.HEALTHY,
                message="Scheduler worker is healthy",
                details={
                    "worker_type": "scheduler",
                    "api_client": "healthy",
                    "queue": "scheduler",
                },
            )
        else:
            return HealthCheckResult(
                name="scheduler_health",
                status=HealthStatus.DEGRADED,
                message="Scheduler worker partially functional",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="scheduler_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check

WorkerRegistry.register_health_check(
    WorkerType.SCHEDULER, "scheduler_health", check_scheduler_health
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "scheduler",
        "task_id": self.request.id,
        "worker_name": config.worker_name if config else "scheduler-worker",
    }
