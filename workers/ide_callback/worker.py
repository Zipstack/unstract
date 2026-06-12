"""IDE Callback Worker

Celery worker for Prompt Studio IDE post-execution callbacks.
Serves the ``ide_callback`` queue defined in shared/infrastructure/config/registry.py.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker - this executes when module is imported by Celery
logger = WorkerLogger.setup(WorkerType.IDE_CALLBACK)
app, config = WorkerBuilder.build_celery_app(WorkerType.IDE_CALLBACK)


def check_ide_callback_health():
    """Custom health check for IDE callback worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.utils.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="ide_callback_health",
                status=HealthStatus.HEALTHY,
                message="IDE callback worker is healthy",
                details={
                    "worker_type": "ide_callback",
                    "api_client": "healthy",
                    "queue": "ide_callback",
                },
            )
        else:
            return HealthCheckResult(
                name="ide_callback_health",
                status=HealthStatus.DEGRADED,
                message="IDE callback worker partially functional",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="ide_callback_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check
WorkerRegistry.register_health_check(
    WorkerType.IDE_CALLBACK, "ide_callback_health", check_ide_callback_health
)
