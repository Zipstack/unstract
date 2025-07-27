#!/usr/bin/env python3
"""Router Worker - Main Entry Point

Routes workflow executions to specialized workers based on execution type.
This implements the exact same pattern as the Django backend router task.
"""

import logging

from celery import Celery
from shared.config import WorkerConfig
from shared.health import HealthServer
from shared.logging_utils import WorkerLogger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize configuration
config = WorkerConfig()

# Create Celery app with router-specific configuration
app = Celery("router_worker")

# Configure Celery with router worker settings
app.conf.update(
    broker_url=config.celery_broker_url,
    result_backend=config.celery_result_backend,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=config.celery_worker_prefetch_multiplier,
    task_acks_late=config.celery_task_acks_late,
    worker_max_tasks_per_child=config.celery_worker_max_tasks_per_child,
    # Router-specific configuration
    task_routes={
        "async_execute_bin": {"queue": "celery"},
        "async_execute_bin_general": {"queue": "celery"},
        "async_execute_bin_api": {"queue": "celery_api_deployments"},
    },
    # Worker configuration
    worker_concurrency=config.max_concurrent_tasks,
    task_soft_time_limit=config.task_timeout - 30,
    task_time_limit=config.task_timeout,
    # Task discovery
    imports=[
        "router.tasks",
    ],
)

# Initialize worker logger
worker_logger = WorkerLogger(
    worker_name=config.worker_name,
    log_level=config.log_level,
    log_format=config.log_format,
    log_file=config.log_file,
)


# Start health server
def start_health_server():
    """Start health check server for router worker."""
    try:
        health_server = HealthServer(
            port=config.metrics_port,
            worker_name=config.worker_name,
            check_interval=config.health_check_interval,
            timeout=config.health_check_timeout,
        )

        # Add router-specific health checks
        health_server.add_custom_check(
            name="router_specific",
            check_func=lambda: {"status": "healthy", "router_type": "workflow_execution"},
        )

        health_server.start()
        logger.info(f"Router worker health server started on port {config.metrics_port}")

    except Exception as e:
        logger.error(f"Failed to start health server: {e}")


if __name__ == "__main__":
    logger.info(f"Router worker initialized with config: {config}")

    # Start health server
    start_health_server()

    # Start Celery worker
    app.worker_main(
        [
            "worker",
            "--loglevel=info",
            "--queues=celery,celery_api_deployments",
            f"--concurrency={config.max_concurrent_tasks}",
            "--hostname=router-worker-prod-01@%h",
        ]
    )
