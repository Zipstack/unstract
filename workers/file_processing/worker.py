"""File Processing Worker

Celery worker for document processing and file handling.
Handles file uploads, text extraction, and processing workflows.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.FILE_PROCESSING)
app, config = WorkerBuilder.build_celery_app(WorkerType.FILE_PROCESSING)


def check_file_processing_health():
    """Custom health check for file processing worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.legacy.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="file_processing_health",
                status=HealthStatus.HEALTHY,
                message="File processing worker is healthy",
                details={
                    "worker_type": "file_processing",
                    "api_client": "healthy",
                    "queues": ["file_processing", "api_file_processing"],
                },
            )
        else:
            return HealthCheckResult(
                name="file_processing_health",
                status=HealthStatus.DEGRADED,
                message="File processing worker partially functional",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="file_processing_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check

WorkerRegistry.register_health_check(
    WorkerType.FILE_PROCESSING, "file_processing_health", check_file_processing_health
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "file_processing",
        "task_id": self.request.id,
        "worker_name": config.worker_name if config else "file-processing-worker",
    }
