"""Scheduler Worker Configuration

Celery worker for scheduled pipeline executions.
Handles execute_pipeline_task and execute_pipeline_task_v2 tasks.
"""

import os

from celery import Celery
from shared.config import WorkerConfig
from shared.logging_utils import WorkerLogger

# Configure worker-specific logging
WorkerLogger.configure(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format=os.getenv("LOG_FORMAT", "structured"),
    worker_name="scheduler-worker",
)

logger = WorkerLogger.get_logger(__name__)

# Initialize configuration with scheduler worker specific settings
config = WorkerConfig.from_env("SCHEDULER")

# Override worker name if not set via environment
if not os.getenv("SCHEDULER_WORKER_NAME"):
    config.worker_name = "scheduler-worker"

# Celery application configuration
app = Celery("scheduler_worker")

# Get queue names from environment or use defaults
scheduler_queue_name = os.getenv("SCHEDULER_QUEUE_NAME", "scheduler")

# Celery settings using standard dictionary pattern like other workers
celery_config = {
    # Broker configuration
    "broker_url": config.celery_broker_url,
    "result_backend": config.celery_result_backend,
    # Task routing - route to scheduler queue
    "task_routes": {
        "execute_pipeline_task": {"queue": scheduler_queue_name},
        "execute_pipeline_task_v2": {"queue": scheduler_queue_name},
        "scheduler_health_check": {"queue": scheduler_queue_name},
        "scheduler.tasks.*": {"queue": scheduler_queue_name},
    },
    # Standard worker configuration
    "worker_disable_rate_limits": True,
    "task_reject_on_worker_lost": True,
    "task_ignore_result": False,
    # Worker performance settings
    "worker_prefetch_multiplier": 1,
    "task_acks_late": True,
    "worker_max_tasks_per_child": 1000,
    # Task timeouts (longer for workflow executions)
    "task_time_limit": config.task_timeout,
    "task_soft_time_limit": config.task_timeout - 30,
    # Serialization
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    # Timezone settings
    "timezone": "UTC",
    "enable_utc": True,
    # Additional shared config (overrides any duplicates)
    **config.get_celery_config(),
    # Task discovery
    "imports": [
        "scheduler.tasks",
    ],
}

app.config_from_object(celery_config)

logger.info(f"Scheduler worker initialized with config: {config}")
logger.info(f"Scheduler queue name: {scheduler_queue_name}")

if __name__ == "__main__":
    """Run worker directly for testing."""
    logger.info("Starting scheduler worker...")

    try:
        # Start Celery worker using standard pattern
        app.start(["worker", "--loglevel=info", f"--queues={scheduler_queue_name}"])
    except KeyboardInterrupt:
        logger.info("Scheduler worker shutdown requested")
    except Exception as e:
        logger.error(f"Scheduler worker failed to start: {e}")
    finally:
        logger.info("Scheduler worker stopped")
