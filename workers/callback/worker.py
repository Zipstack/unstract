"""Callback Worker

Celery worker for processing file processing callbacks and status updates.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.CALLBACK)
app, config = WorkerBuilder.build_celery_app(WorkerType.CALLBACK)


def check_callback_health():
    """Custom health check for callback worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.legacy.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="callback_health",
                status=HealthStatus.HEALTHY,
                message="Callback worker is healthy",
                details={
                    "worker_type": "callback",
                    "api_client": "healthy",
                    "queues": [
                        "file_processing_callback",
                        "api_file_processing_callback",
                    ],
                },
            )
        else:
            return HealthCheckResult(
                name="callback_health",
                status=HealthStatus.DEGRADED,
                message="Callback worker partially functional",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="callback_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check

WorkerRegistry.register_health_check(
    WorkerType.CALLBACK, "callback_health", check_callback_health
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "callback",
        "task_id": self.request.id,
        "worker_name": config.worker_name if config else "callback-worker",
    }
