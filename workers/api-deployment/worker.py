"""API Deployment Worker

Celery worker for API deployment workflows.
Handles API deployment, cleanup, and status checking tasks.
"""

from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.config.registry import WorkerRegistry
from shared.infrastructure.logging import WorkerLogger

# Setup worker
logger = WorkerLogger.setup(WorkerType.API_DEPLOYMENT)
app, config = WorkerBuilder.build_celery_app(WorkerType.API_DEPLOYMENT)


def check_api_deployment_health():
    """Custom health check for API deployment worker."""
    from shared.infrastructure.monitoring.health import HealthCheckResult, HealthStatus

    try:
        from shared.legacy.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        api_healthy = client is not None

        if api_healthy:
            return HealthCheckResult(
                name="api_deployment_health",
                status=HealthStatus.HEALTHY,
                message="API deployment worker is healthy",
                details={
                    "worker_type": "api_deployment",
                    "api_client": "healthy",
                    "queue": "celery_api_deployments",
                },
            )
        else:
            return HealthCheckResult(
                name="api_deployment_health",
                status=HealthStatus.DEGRADED,
                message="API connectivity degraded",
                details={"api_client": "unhealthy"},
            )

    except Exception as e:
        return HealthCheckResult(
            name="api_deployment_health",
            status=HealthStatus.UNHEALTHY,
            message=f"Health check failed: {e}",
            details={"error": str(e)},
        )


# Register health check

WorkerRegistry.register_health_check(
    WorkerType.API_DEPLOYMENT, "api_deployment_health", check_api_deployment_health
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring systems."""
    return {
        "status": "healthy",
        "worker_type": "api_deployment",
        "task_id": self.request.id,
        "worker_name": config.worker_name if config else "api-deployment-worker",
    }
