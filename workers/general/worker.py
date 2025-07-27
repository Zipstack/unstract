"""General Worker Configuration

Lightweight Celery worker for general tasks including webhooks and background processing.
"""

import os

from celery import Celery

# Import shared worker infrastructure
from shared.config import WorkerConfig
from shared.health import HealthChecker, HealthServer
from shared.logging_utils import WorkerLogger

# Configure worker-specific logging
WorkerLogger.configure(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format=os.getenv("LOG_FORMAT", "structured"),
    worker_name="general-worker",
)

logger = WorkerLogger.get_logger(__name__)

# Initialize configuration with general worker specific settings
config = WorkerConfig.from_env("GENERAL")

# Override worker name if not set via environment
if not os.getenv("GENERAL_WORKER_NAME"):
    config.worker_name = "general-worker"

# Celery application configuration
app = Celery("general_worker")

# Celery settings
celery_config = {
    # Broker configuration
    "broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    "result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    # Task routing - route to general/celery queue
    "task_routes": {
        "send_webhook_notification": {"queue": "celery"},
        "async_execute_bin": {"queue": "celery"},
        "async_execute_bin_general": {"queue": "celery"},
        "general_worker.*": {"queue": "celery"},
    },
    # Task filtering - reject API deployment tasks
    "worker_disable_rate_limits": True,
    "task_reject_on_worker_lost": True,
    "task_ignore_result": False,
    # Worker configuration
    "worker_prefetch_multiplier": 1,
    "task_acks_late": True,
    "worker_max_tasks_per_child": 1000,
    # Task timeouts
    "task_time_limit": config.task_timeout,
    "task_soft_time_limit": config.task_timeout - 30,
    # Logging
    "worker_log_format": "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    "worker_task_log_format": "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
    # Serialization
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    # Additional shared config
    **config.get_celery_config(),
}

app.config_from_object(celery_config)

# Handle both API and ETL/TASK workflows in general worker
# The Django backend sends async_execute_bin_api for both API and ETL/TASK workflows
# We need to detect the actual workflow type and handle accordingly

# Initialize health monitoring
health_checker = HealthChecker(config)


# Add custom health check for general worker
def check_general_worker_health():
    """Custom health check for general worker."""
    from shared.health import HealthCheckResult, HealthStatus

    try:
        # Check if we can access general worker specific resources
        from shared.api_client import InternalAPIClient

        with InternalAPIClient(config) as client:
            # Test API connectivity
            health_response = client.health_check()

            # Test webhook functionality (dry run)
            try:
                webhook_test = client.test_webhook(
                    url="https://httpbin.org/post",
                    payload={"test": "health_check"},
                    timeout=5,
                )
                webhook_success = webhook_test.get("success", False)
            except Exception:
                webhook_success = False

            if health_response.get("status") == "healthy" and webhook_success:
                return HealthCheckResult(
                    name="general_worker_specific",
                    status=HealthStatus.HEALTHY,
                    message="General worker specific checks passed",
                    details={
                        "api_health": health_response,
                        "webhook_test": webhook_success,
                    },
                )
            else:
                return HealthCheckResult(
                    name="general_worker_specific",
                    status=HealthStatus.DEGRADED,
                    message="General worker partially functional",
                    details={
                        "api_health": health_response,
                        "webhook_test": webhook_success,
                    },
                )

    except Exception as e:
        return HealthCheckResult(
            name="general_worker_specific",
            status=HealthStatus.UNHEALTHY,
            message=f"General worker health check failed: {str(e)}",
            details={"error": str(e)},
        )


health_checker.add_custom_check("general_worker_specific", check_general_worker_health)

# Start health server (use different port than API deployment worker)
health_server = HealthServer(health_checker, port=config.metrics_port + 1)


def start_health_server():
    """Start health monitoring server."""
    try:
        health_server.start()
        logger.info(
            f"General worker health server started on port {config.metrics_port + 1}"
        )
    except Exception as e:
        logger.error(f"Failed to start health server: {e}")


def stop_health_server():
    """Stop health monitoring server."""
    try:
        health_server.stop()
        logger.info("General worker health server stopped")
    except Exception as e:
        logger.error(f"Failed to stop health server: {e}")


# Import tasks directly

logger.info(f"General worker initialized with config: {config}")

# Start health server when module is imported
start_health_server()

if __name__ == "__main__":
    """Run worker directly for testing."""
    logger.info("Starting general worker...")

    try:
        # Run initial health check
        health_report = health_checker.run_all_checks()
        logger.info(f"Initial health status: {health_report['status']}")

        # Start Celery worker
        app.start(["worker", "--loglevel=info", "--queues=celery"])

    except KeyboardInterrupt:
        logger.info("General worker shutdown requested")
    except Exception as e:
        logger.error(f"General worker failed to start: {e}")
    finally:
        stop_health_server()
        logger.info("General worker stopped")
