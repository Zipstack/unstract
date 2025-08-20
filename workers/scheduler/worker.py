#!/usr/bin/env python3
"""Scheduler Worker Configuration

Celery worker for scheduled pipeline executions.
Handles execute_pipeline_task and execute_pipeline_task_v2 tasks.
"""

import os

# Clear Django settings to avoid Celery warning about Django not being installed
# This is set by the backend but not needed in workers
os.environ.pop("DJANGO_SETTINGS_MODULE", None)

from celery import Celery  # noqa: E402

# Use singleton API client to eliminate repeated initialization logs
from shared.config import WorkerConfig  # noqa: E402
from shared.health import HealthChecker, HealthServer  # noqa: E402
from shared.logging_utils import WorkerLogger  # noqa: E402

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

# Celery settings
celery_config = {
    # Broker configuration
    "broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    "result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    # Task routing - route to scheduler queue
    "task_routes": {
        "execute_pipeline_task": {"queue": "scheduler"},
        "execute_pipeline_task_v2": {"queue": "scheduler"},
        "scheduler_health_check": {"queue": "scheduler"},
        "scheduler.tasks.*": {"queue": "scheduler"},
    },
    # Worker configuration for scheduled tasks
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
    # Logging
    "worker_log_format": "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    "worker_task_log_format": "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
    # Serialization
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    # Timezone settings
    "timezone": "UTC",
    "enable_utc": True,
    # Additional shared config from WorkerConfig
    **config.get_celery_config(),
    # Task discovery
    "imports": [
        "scheduler.tasks",
    ],
}

app.config_from_object(celery_config)

# Initialize health monitoring
health_checker = HealthChecker(config)
health_server = HealthServer(
    health_checker=health_checker, port=int(os.getenv("SCHEDULER_HEALTH_PORT", "8087"))
)

logger.info(
    f"Scheduler worker configured - Queue: scheduler, Health: {os.getenv('SCHEDULER_HEALTH_PORT', '8087')}, Timeout: {config.task_timeout}s"
)

if __name__ == "__main__":
    logger.info(f"Starting Scheduler Worker with config: {config}")

    # Start health server
    health_server.start()

    try:
        # Start Celery worker
        app.worker_main(
            [
                "worker",
                "--loglevel=info",
                "--pool=prefork",
                "--concurrency=2",
                "--queues=scheduler",
            ]
        )
    except KeyboardInterrupt:
        logger.info("Shutting down Scheduler Worker...")
    finally:
        # Stop health server
        health_server.stop()
