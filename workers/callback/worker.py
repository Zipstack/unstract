"""Lightweight File Processing Callback Worker

Handles result aggregation and execution finalization using internal APIs.
"""

import os

from celery import Celery
from shared.config import WorkerConfig
from shared.health import HealthChecker, HealthServer
from shared.logging_utils import WorkerLogger

# Initialize configuration with callback-specific settings
config = WorkerConfig.from_env("CALLBACK")

# Configure logging to match Django backend
WorkerLogger.configure(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format=os.getenv("LOG_FORMAT", "django"),  # Use Django-style logging
    worker_name="callback-worker",
)

# Initialize logger
logger = WorkerLogger.get_logger(__name__)

# Initialize Celery app
app = Celery("file_processing_callback_worker")

# Configure Celery
app.conf.update(
    broker_url=config.celery_broker_url,
    result_backend=config.celery_result_backend,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker configuration
    worker_prefetch_multiplier=int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1")),
    task_acks_late=os.getenv("CELERY_TASK_ACKS_LATE", "true").lower() == "true",
    worker_max_tasks_per_child=int(
        os.getenv("CELERY_WORKER_MAX_TASKS_PER_CHILD", "1000")
    ),
    # Queue configuration
    task_routes={
        "process_batch_callback": {"queue": "file_processing_callback"},
        "process_batch_callback_api": {"queue": "api_file_processing_callback"},
        "finalize_execution_callback": {"queue": "file_processing_callback"},
    },
    # Task configuration
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=True,
    worker_disable_rate_limits=False,
    # Retry configuration
    task_default_retry_delay=60,
    task_max_retries=3,
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
    # Task discovery
    imports=[
        "callback.tasks",
    ],
)

# Initialize metrics
# TODO: Fix metrics import - metrics = init_metrics("callback")

# Initialize health checker and server

health_checker = HealthChecker(config)
health_server = HealthServer(
    health_checker=health_checker, port=int(os.getenv("CALLBACK_HEALTH_PORT", "8083"))
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring."""
    return {"status": "healthy", "worker_type": "callback", "task_id": self.request.id}


# Tasks are imported via Celery imports configuration above

if __name__ == "__main__":
    logger.info(f"Starting File Processing Callback Worker with config: {config}")

    # Start health server
    health_server.start()

    try:
        # Start Celery worker
        app.worker_main(
            [
                "worker",
                "--loglevel=info",
                "--autoscale=4,1",
                "--queues=file_processing_callback,api_file_processing_callback",
            ]
        )
    except KeyboardInterrupt:
        logger.info("Shutting down File Processing Callback Worker...")
    finally:
        # Stop health server
        health_server.stop()
