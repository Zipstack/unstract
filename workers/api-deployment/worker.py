"""API Deployment Worker Configuration

Lightweight Celery worker for API deployment workflows.
"""

import os

from celery import Celery

# Import shared worker infrastructure
from shared import HealthChecker, HealthServer, WorkerConfig, WorkerLogger

# Configure worker-specific logging to match Django backend
WorkerLogger.configure(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format=os.getenv("LOG_FORMAT", "django"),  # Use Django-style logging
    worker_name="api-deployment-worker",
)

logger = WorkerLogger.get_logger(__name__)

# Initialize configuration with API deployment specific settings
config = WorkerConfig.from_env("API_DEPLOYMENT")

# Override worker name if not set via environment
if not os.getenv("API_DEPLOYMENT_WORKER_NAME"):
    config.worker_name = "api-deployment-worker"

# Celery application configuration
app = Celery("api_deployment_worker")

# Configure Celery using shared configuration (matches backend patterns)
celery_config = config.get_celery_config()

# Override task routes for API deployment worker
celery_config.update(
    {
        "task_routes": {
            "async_execute_bin_api": {"queue": "celery_api_deployments"},
            "api_deployment_cleanup": {"queue": "celery_api_deployments"},
            "api_deployment_status_check": {"queue": "celery_api_deployments"},
            "api_deployment_worker.*": {"queue": "celery_api_deployments"},
        },
        # Task discovery
        "imports": [
            "api-deployment.tasks",
        ],
    }
)

app.conf.update(celery_config)

# Initialize health monitoring
health_checker = HealthChecker(config)


# Add custom health check for API deployment worker
def check_api_deployment_health():
    """Custom health check for API deployment worker."""
    from shared.health import HealthCheckResult, HealthStatus

    try:
        # Check if we can access API deployment specific resources
        from shared.api_client_singleton import get_singleton_api_client

        client = get_singleton_api_client(config)
        # Simply check if API client is available (avoid making actual calls)
        try:
            # If we can create the client, API connectivity is considered healthy
            api_healthy = client is not None
            api_status = "healthy" if api_healthy else "unhealthy"
        except Exception:
            api_healthy = False
            api_status = "unhealthy"

        if api_healthy:
            return HealthCheckResult(
                name="api_deployment_specific",
                status=HealthStatus.HEALTHY,
                message="API deployment worker specific checks passed",
                details={"api_health": api_status},
            )
        else:
            return HealthCheckResult(
                name="api_deployment_specific",
                status=HealthStatus.DEGRADED,
                message="API connectivity degraded",
                details={
                    "api_health": api_status if "api_status" in locals() else "unknown"
                },
            )

    except Exception as e:
        return HealthCheckResult(
            name="api_deployment_specific",
            status=HealthStatus.UNHEALTHY,
            message=f"API deployment health check failed: {str(e)}",
            details={"error": str(e)},
        )


health_checker.add_custom_check("api_deployment_specific", check_api_deployment_health)

# Start health server
health_server = HealthServer(health_checker, port=config.metrics_port)


def start_health_server():
    """Start health monitoring server."""
    try:
        health_server.start()
        logger.info(
            f"API deployment worker health server started on port {config.metrics_port}"
        )
    except Exception as e:
        logger.error(f"Failed to start health server: {e}")


def stop_health_server():
    """Stop health monitoring server."""
    try:
        health_server.stop()
        logger.info("API deployment worker health server stopped")
    except Exception as e:
        logger.error(f"Failed to stop health server: {e}")


# Import tasks directly instead of autodiscovery

logger.info(f"API deployment worker initialized with config: {config}")

# Don't auto-start health server - let entrypoint.py handle it

if __name__ == "__main__":
    """Run worker directly for testing."""
    logger.info("Starting API deployment worker...")

    try:
        # Run initial health check
        health_report = health_checker.run_all_checks()
        logger.info(f"Initial health status: {health_report['status']}")

        # Start Celery worker
        app.worker_main(["worker", "--loglevel=info", "--queues=celery_api_deployments"])

    except KeyboardInterrupt:
        logger.info("API deployment worker shutdown requested")
    except Exception as e:
        logger.error(f"API deployment worker failed to start: {e}")
    finally:
        stop_health_server()
        logger.info("API deployment worker stopped")
