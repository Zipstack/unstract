"""Log Consumer Worker

Celery worker for processing execution logs and WebSocket emissions.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.LOG_CONSUMER)
app, config = WorkerBuilder.build_celery_app(WorkerType.LOG_CONSUMER)


def check_log_consumer_health():
    """Custom health check for log consumer worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.legacy.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="log_consumer_health",
                status=HealthStatus.HEALTHY,
                message="Log consumer worker is healthy",
                details={
                    "worker_type": "log_consumer",
                    "api_client": "healthy",
                    "queues": ["celery_log_task_queue", "celery_periodic_logs"],
                },
            )
        else:
            return HealthCheckResult(
                name="log_consumer_health",
                status=HealthStatus.DEGRADED,
                message="Log consumer worker partially functional",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="log_consumer_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check

WorkerRegistry.register_health_check(
    WorkerType.LOG_CONSUMER, "log_consumer_health", check_log_consumer_health
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "log_consumer",
        "task_id": self.request.id,
        "worker_name": config.worker_name if config else "log-consumer-worker",
    }
