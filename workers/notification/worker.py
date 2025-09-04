"""Notification Worker

Celery worker for processing notifications including webhooks, emails, SMS.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.NOTIFICATION)
app, config = WorkerBuilder.build_celery_app(WorkerType.NOTIFICATION)


def check_notification_health():
    """Custom health check for notification worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.legacy.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="notification_health",
                status=HealthStatus.HEALTHY,
                message="Notification worker is healthy",
                details={
                    "worker_type": "notification",
                    "api_client": "healthy",
                    "queues": [
                        "notifications_webhook",
                        "notifications_email",
                        "notifications_sms",
                    ],
                },
            )
        else:
            return HealthCheckResult(
                name="notification_health",
                status=HealthStatus.DEGRADED,
                message="Notification worker partially functional",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="notification_health",
            status=HealthStatus.DEGRADED,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check

WorkerRegistry.register_health_check(
    WorkerType.NOTIFICATION, "notification_health", check_notification_health
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "notification",
        "task_id": self.request.id,
        "worker_name": config.worker_name if config else "notification-worker",
    }
