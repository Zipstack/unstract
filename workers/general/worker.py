"""General Worker

Celery worker for general tasks including webhooks, background
processing, and workflow orchestration.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.GENERAL)
app, config = WorkerBuilder.build_celery_app(WorkerType.GENERAL)


def check_general_worker_health():
    """Custom health check for general worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.legacy.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="general_worker_health",
                status=HealthStatus.HEALTHY,
                message="General worker is healthy",
                details={
                    "worker_type": "general",
                    "api_client": "healthy",
                    "queue": "celery",
                },
            )
        else:
            return HealthCheckResult(
                name="general_worker_health",
                status=HealthStatus.DEGRADED,
                message="General worker partially functional",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="general_worker_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check

WorkerRegistry.register_health_check(
    WorkerType.GENERAL, "general_worker_health", check_general_worker_health
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "general",
        "task_id": self.request.id,
        "worker_name": config.worker_name if config else "general-worker",
    }
