"""Lightweight File Processing Worker

Handles file processing tasks using internal APIs instead of direct Django ORM access.
This replaces the heavy Django workers for file processing operations.
"""

import os

from celery import Celery
from monitoring.prometheus_metrics import init_metrics
from shared.config import WorkerConfig
from shared.health import HealthChecker, HealthServer
from shared.logging_utils import WorkerLogger

# Initialize configuration
config = WorkerConfig()

# Configure logging to match Django backend
WorkerLogger.configure(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format=os.getenv("LOG_FORMAT", "django"),  # Use Django-style logging
    worker_name="file-processing-worker",
)

# Initialize logger
logger = WorkerLogger.get_logger(__name__)

# Initialize Celery app
app = Celery("file_processing_worker")

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
        "process_file_batch": {"queue": "file_processing"},
        "process_file_batch_api": {"queue": "api_file_processing"},
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
)

# Initialize metrics
metrics = init_metrics("file_processing")

# Initialize health checker and server

health_checker = HealthChecker(config)
health_server = HealthServer(
    health_checker=health_checker,
    port=int(os.getenv("FILE_PROCESSING_HEALTH_PORT", "8082")),
)


@app.task(bind=True)
def healthcheck(self):
    """Health check task for monitoring."""
    return {
        "status": "healthy",
        "worker_type": "file_processing",
        "task_id": self.request.id,
    }


# Import tasks after app configuration

if __name__ == "__main__":
    logger.info(f"Starting File Processing Worker with config: {config}")

    # Start health server
    health_server.start()

    try:
        # Start Celery worker
        app.worker_main(
            [
                "worker",
                "--loglevel=info",
                "--pool=threads",
                "--concurrency=4",
                "--queues=file_processing,api_file_processing",
            ]
        )
    except KeyboardInterrupt:
        logger.info("Shutting down File Processing Worker...")
    finally:
        # Stop health server
        health_server.stop()
