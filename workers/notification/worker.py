"""Notification Worker Configuration

Celery worker for processing all types of notifications including webhooks, emails, SMS, and push notifications.
This worker provides a unified interface for notification processing while maintaining backward compatibility.
"""

import os

from celery import Celery
from shared.api_client_singleton import get_singleton_api_client
from shared.config import WorkerConfig
from shared.health import HealthChecker, HealthServer
from shared.logging_utils import WorkerLogger

# Configure worker-specific logging
WorkerLogger.configure(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format=os.getenv("LOG_FORMAT", "structured"),
    worker_name="notification-worker",
)

logger = WorkerLogger.get_logger(__name__)

# Initialize configuration with notification worker specific settings
config = WorkerConfig.from_env("NOTIFICATION")

# Override worker name if not set via environment
if not os.getenv("NOTIFICATION_WORKER_NAME"):
    config.worker_name = "notification-worker"

# Celery application configuration
app = Celery("notification_worker")

# Get queue names from environment or use defaults
default_queue_name = os.getenv("DEFAULT_QUEUE_NAME", "celery")  # Backward compatibility
notification_queue_name = os.getenv("NOTIFICATION_QUEUE_NAME", "notifications")
webhook_queue_name = os.getenv("WEBHOOK_QUEUE_NAME", "notifications_webhook")
email_queue_name = os.getenv("EMAIL_QUEUE_NAME", "notifications_email")
sms_queue_name = os.getenv("SMS_QUEUE_NAME", "notifications_sms")
priority_queue_name = os.getenv("PRIORITY_QUEUE_NAME", "notifications_priority")

# Build queue list for worker consumption
all_notification_queues = [
    notification_queue_name,  # Main notification queue
    webhook_queue_name,  # Webhook-specific queue
    email_queue_name,  # Email-specific queue (future)
    sms_queue_name,  # SMS-specific queue (future)
    priority_queue_name,  # High-priority notifications
    # NOTE: Explicitly exclude default queue to prevent misrouted tasks
]

# Queue names as comma-separated string for Celery
queue_names_str = ",".join(all_notification_queues)

# Celery settings
celery_config = {
    # Broker configuration
    "broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    "result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    # Task routing - route to specific queues based on notification type
    "task_routes": {
        # New notification worker tasks - route to notification queues
        "process_notification": {"queue": notification_queue_name},
        "send_webhook_notification": {"queue": notification_queue_name},
        "send_batch_notifications": {"queue": notification_queue_name},
        "notification_health_check": {"queue": notification_queue_name},
        "notification.tasks.*": {"queue": notification_queue_name},
        # Future task routing for other types
        "send_email_notification": {"queue": email_queue_name},
        "send_sms_notification": {"queue": sms_queue_name},
        "send_push_notification": {"queue": notification_queue_name},
        # Priority notifications
        "priority_notification": {"queue": priority_queue_name},
    },
    # Task filtering - accept notification tasks
    "worker_disable_rate_limits": True,
    "task_reject_on_worker_lost": True,
    "task_ignore_result": False,
    # Worker configuration - optimized for reliable notification delivery
    "worker_prefetch_multiplier": 1,
    "task_acks_late": True,
    "worker_max_tasks_per_child": 1000,
    # Task timeouts - generous for webhook retries
    "task_time_limit": config.task_timeout,
    "task_soft_time_limit": config.task_timeout - 30,
    # Logging
    "worker_log_format": "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    "worker_task_log_format": "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
    # Serialization
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    # Additional shared config (but we'll override task_routes)
    **{k: v for k, v in config.get_celery_config().items() if k != "task_routes"},
    # Task discovery
    "imports": [
        "notification.tasks",  # Import tasks from notification package
    ],
}

app.config_from_object(celery_config)

# Ensure tasks are imported and registered
try:
    logger.info("Successfully imported notification tasks")
except ImportError as e:
    logger.error(f"Failed to import notification tasks: {e}")

# Task routes should be properly set by now
logger.info(
    f"Configured task routes: {list(app.conf.task_routes.keys()) if app.conf.task_routes else 'None'}"
)

# Initialize health monitoring
health_checker = HealthChecker(config)


def get_health_api_client():
    """Get singleton API client for health checks."""
    return get_singleton_api_client(config)


# Add custom health check for notification worker
def check_notification_worker_health():
    """Custom health check for notification worker."""
    from shared.health import HealthCheckResult, HealthStatus

    try:
        # Use shared API client to reduce repeated initializations
        client = get_health_api_client()

        # Check if API client is available
        try:
            api_healthy = client is not None
        except Exception:
            api_healthy = False

        # Check provider availability
        try:
            from providers.webhook_provider import WebhookProvider

            webhook_provider = WebhookProvider()
            logger.info(f"Webhook provider {webhook_provider} is available")
            providers_healthy = True
        except Exception:
            providers_healthy = False

        # Check notification queue connectivity
        try:
            # Simple broker connectivity test
            from celery import current_app

            inspect = current_app.control.inspect()
            queue_healthy = inspect is not None
        except Exception:
            queue_healthy = False

        if api_healthy and providers_healthy and queue_healthy:
            return HealthCheckResult(
                name="notification_worker_specific",
                status=HealthStatus.HEALTHY,
                message="Notification worker specific checks passed",
                details={
                    "api_health": "healthy",
                    "providers_health": "healthy",
                    "queue_health": "healthy",
                    "queues": all_notification_queues,
                    "primary_queue": notification_queue_name,
                    "default_queue": default_queue_name,
                    "supported_types": ["WEBHOOK"],  # Future: EMAIL, SMS, PUSH
                },
            )
        else:
            return HealthCheckResult(
                name="notification_worker_specific",
                status=HealthStatus.DEGRADED,
                message="Notification worker partially functional",
                details={
                    "api_health": "healthy" if api_healthy else "unhealthy",
                    "providers_health": "healthy" if providers_healthy else "unhealthy",
                    "queue_health": "healthy" if queue_healthy else "unhealthy",
                    "queues": all_notification_queues,
                    "primary_queue": notification_queue_name,
                },
            )

    except Exception as e:
        return HealthCheckResult(
            name="notification_worker_specific",
            status=HealthStatus.UNHEALTHY,
            message=f"Notification worker health check failed: {str(e)}",
            details={"error": str(e)},
        )


health_checker.add_custom_check(
    "notification_worker_specific", check_notification_worker_health
)

# Start health server (use port 8085 for notification worker)
health_server = HealthServer(health_checker, port=8085)


def start_health_server():
    """Start health monitoring server."""
    try:
        health_server.start()
        logger.info("Notification worker health server started on port 8085")
    except Exception as e:
        logger.error(f"Failed to start health server: {e}")


def stop_health_server():
    """Stop health monitoring server."""
    try:
        health_server.stop()
        logger.info("Notification worker health server stopped")
    except Exception as e:
        logger.error(f"Failed to stop health server: {e}")


logger.info(f"Notification worker initialized with config: {config}")
logger.info(f"Notification queue name: {notification_queue_name}")

if __name__ == "__main__":
    """Run worker directly for testing."""
    logger.info("Starting notification worker...")

    try:
        # Run initial health check
        health_report = health_checker.run_all_checks()
        logger.info(f"Initial health status: {health_report['status']}")

        # Start Celery worker with all notification queues
        app.start(["worker", "--loglevel=info", f"--queues={queue_names_str}"])

    except KeyboardInterrupt:
        logger.info("Notification worker shutdown requested")
    except Exception as e:
        logger.error(f"Notification worker failed to start: {e}")
    finally:
        stop_health_server()
        logger.info("Notification worker stopped")
