"""Structure Extraction Worker

Celery worker for structure tool execution.
Replaces Docker-based structure tool with Celery task execution.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.STRUCTURE)
app, config = WorkerBuilder.build_celery_app(WorkerType.STRUCTURE)


def check_structure_health():
    """Custom health check for structure worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.utils.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="structure_health",
                status=HealthStatus.HEALTHY,
                message="Structure worker is healthy",
                details={
                    "worker_type": "structure",
                    "api_client": "healthy",
                    "queues": ["structure_extraction"],
                },
            )
        else:
            return HealthCheckResult(
                name="structure_health",
                status=HealthStatus.DEGRADED,
                message="Structure worker partially functional",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="structure_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check
WorkerRegistry.register_health_check(
    WorkerType.STRUCTURE, "structure_health", check_structure_health
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "structure",
        "task_id": self.request.id,
        "worker_name": config.worker_name if config else "structure-worker",
    }
