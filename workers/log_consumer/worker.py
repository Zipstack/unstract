"""Log Consumer Worker Configuration

Lightweight Celery worker for processing execution logs and WebSocket emissions.
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
    worker_name="log-consumer-worker",
)

logger = WorkerLogger.get_logger(__name__)

# Initialize configuration with log consumer specific settings
config = WorkerConfig.from_env("LOG_CONSUMER")

# Override worker name if not set via environment
if not os.getenv("LOG_CONSUMER_WORKER_NAME"):
    config.worker_name = "log-consumer-worker"

# Celery application configuration
app = Celery("log_consumer_worker")

# Get queue names from environment or use defaults (support multiple queues)
log_consumer_queues = os.getenv("LOG_CONSUMER_QUEUE_NAME", "celery_log_task_queue")
periodic_logs_queue = os.getenv("PERIODIC_LOGS_QUEUE_NAME", "celery_periodic_logs")

# Support comma-separated queue names for flexibility
if "," in log_consumer_queues:
    queue_names = [q.strip() for q in log_consumer_queues.split(",")]
else:
    # Default queues for log consumer worker
    queue_names = [log_consumer_queues, periodic_logs_queue]

# Remove duplicates while preserving order
all_queues = []
seen = set()
for queue in queue_names:
    if queue not in seen:
        all_queues.append(queue)
        seen.add(queue)

queue_names_str = ",".join(all_queues)

# Celery settings
celery_config = {
    # Broker configuration
    "broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    "result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    # Task routing - route to appropriate queues
    "task_routes": {
        "logs_consumer": {"queue": log_consumer_queues},
        "consume_log_history": {"queue": periodic_logs_queue},
        "log_consumer.tasks.*": {"queue": log_consumer_queues},
        "log_consumer_health_check": {"queue": log_consumer_queues},
    },
    # Task filtering - only accept log processing tasks
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
    # Task discovery
    "imports": [
        "log_consumer.tasks",
    ],
}

app.config_from_object(celery_config)

# Initialize health monitoring
health_checker = HealthChecker(config)


def get_health_api_client():
    """Get singleton API client for health checks."""
    return get_singleton_api_client(config)


# Add custom health check for log consumer worker
def check_log_consumer_health():
    """Custom health check for log consumer worker."""
    from shared.health import HealthCheckResult, HealthStatus

    try:
        # Use shared API client to reduce repeated initializations
        client = get_health_api_client()

        # Check if API client is available
        try:
            api_healthy = client is not None
        except Exception:
            api_healthy = False

        # Check Redis connectivity for log storage
        try:
            from unstract.core.log_utils import create_redis_client

            redis_client = create_redis_client(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                username=os.getenv("REDIS_USER"),
                password=os.getenv("REDIS_PASSWORD"),
            )
            redis_client.ping()
            redis_healthy = True
        except Exception:
            redis_healthy = False

        if api_healthy and redis_healthy:
            return HealthCheckResult(
                name="log_consumer_specific",
                status=HealthStatus.HEALTHY,
                message="Log consumer worker specific checks passed",
                details={
                    "api_health": "healthy",
                    "redis_health": "healthy",
                    "queue_names": queue_names_str,
                },
            )
        else:
            return HealthCheckResult(
                name="log_consumer_specific",
                status=HealthStatus.DEGRADED,
                message="Log consumer worker partially functional",
                details={
                    "api_health": "healthy" if api_healthy else "unhealthy",
                    "redis_health": "healthy" if redis_healthy else "unhealthy",
                    "queue_names": queue_names_str,
                },
            )

    except Exception as e:
        return HealthCheckResult(
            name="log_consumer_specific",
            status=HealthStatus.UNHEALTHY,
            message=f"Log consumer health check failed: {str(e)}",
            details={"error": str(e)},
        )


health_checker.add_custom_check("log_consumer_specific", check_log_consumer_health)

# Start health server (use port 8084 for log consumer)
health_server = HealthServer(health_checker, port=8084)


def start_health_server():
    """Start health monitoring server."""
    try:
        health_server.start()
        logger.info("Log consumer health server started on port 8084")
    except Exception as e:
        logger.error(f"Failed to start health server: {e}")


def stop_health_server():
    """Stop health monitoring server."""
    try:
        health_server.stop()
        logger.info("Log consumer health server stopped")
    except Exception as e:
        logger.error(f"Failed to stop health server: {e}")


logger.info(f"Log consumer worker initialized with config: {config}")
logger.info(f"Log consumer queue names: {queue_names_str}")

if __name__ == "__main__":
    """Run worker directly for testing."""
    logger.info("Starting log consumer worker...")

    try:
        # Run initial health check
        health_report = health_checker.run_all_checks()
        logger.info(f"Initial health status: {health_report['status']}")

        # Start Celery worker with all configured queues
        app.start(["worker", "--loglevel=info", f"--queues={queue_names_str}"])

    except KeyboardInterrupt:
        logger.info("Log consumer worker shutdown requested")
    except Exception as e:
        logger.error(f"Log consumer worker failed to start: {e}")
    finally:
        stop_health_server()
        logger.info("Log consumer worker stopped")
