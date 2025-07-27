"""Example Lightweight Worker Implementation

Demonstrates how to use the shared worker infrastructure for creating
lightweight Celery workers that communicate via internal APIs.
"""

import os
import time
from typing import Any

from celery import Celery

# Import shared data models for type safety
from unstract.core.data_models import ExecutionStatus

from .api_client import InternalAPIClient

# Import shared worker infrastructure
from .config import WorkerConfig
from .health import HealthChecker, HealthServer
from .logging_utils import WorkerLogger, log_context, monitor_performance
from .retry_utils import ResilientExecutor, circuit_breaker, retry

# Configure logging
WorkerLogger.configure(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format="structured",
    worker_name="example-worker",
)

logger = WorkerLogger.get_logger(__name__)

# Initialize configuration
config = WorkerConfig()

# Initialize Celery app
app = Celery("example_worker")
app.config_from_object(
    {
        "broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        "result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
        **config.get_celery_config(),
    }
)

# Initialize health checker
health_checker = HealthChecker(config)


# Add custom health check
def check_worker_specific_health():
    """Custom health check for this worker."""
    from .health import HealthCheckResult, HealthStatus

    # Example: Check if worker can connect to required services
    try:
        # Your worker-specific health logic here
        return HealthCheckResult(
            name="worker_specific",
            status=HealthStatus.HEALTHY,
            message="Worker-specific check passed",
        )
    except Exception as e:
        return HealthCheckResult(
            name="worker_specific",
            status=HealthStatus.UNHEALTHY,
            message=f"Worker-specific check failed: {e}",
        )


health_checker.add_custom_check("worker_specific", check_worker_specific_health)

# Start health server
health_server = HealthServer(health_checker, port=config.metrics_port)
health_server.start()

logger.info(
    f"Example worker initialized with health server on port {config.metrics_port}"
)


@app.task(bind=True)
@monitor_performance
@retry(max_attempts=3, base_delay=1.0)
def example_task(self, execution_id: str, organization_id: str = None) -> dict[str, Any]:
    """Example task demonstrating lightweight worker patterns.

    Args:
        execution_id: Workflow execution ID
        organization_id: Organization context

    Returns:
        Task result
    """
    task_id = self.request.id

    with log_context(
        task_id=task_id, execution_id=execution_id, organization_id=organization_id
    ):
        logger.info(f"Starting example task for execution {execution_id}")

        try:
            # Initialize API client
            with InternalAPIClient(config) as api_client:
                # Set organization context if provided
                if organization_id:
                    api_client.set_organization_context(organization_id)

                # Get workflow execution context via API
                execution_data = api_client.get_workflow_execution(execution_id)
                logger.info(
                    f"Retrieved execution data: {execution_data.get('execution', {}).get('id')}"
                )

                # Update execution status to in progress
                api_client.update_workflow_execution_status(
                    execution_id=execution_id, status="IN_PROGRESS"
                )

                # Simulate some work
                logger.info("Processing workflow execution...")
                time.sleep(2)  # Simulate processing time

                # Example: Create file batch (if needed)
                if execution_data.get("file_executions"):
                    file_batch = api_client.create_file_batch(
                        workflow_execution_id=execution_id,
                        files=[
                            {
                                "file_name": "example.txt",
                                "file_path": "/tmp/example.txt",
                                "file_size": 1024,
                                "mime_type": "text/plain",
                            }
                        ],
                        is_api=True,
                    )
                    logger.info(f"Created file batch: {file_batch.get('batch_id')}")

                # Update execution status to completed
                api_client.update_workflow_execution_status(
                    execution_id=execution_id,
                    status=ExecutionStatus.COMPLETED.value,
                    execution_time=2.0,
                )

                logger.info(f"Completed example task for execution {execution_id}")

                return {
                    "status": "success",
                    "execution_id": execution_id,
                    "task_id": task_id,
                    "processed_at": time.time(),
                }

        except Exception as e:
            logger.error(f"Example task failed for execution {execution_id}: {e}")

            # Try to update execution status to failed
            try:
                with InternalAPIClient(config) as api_client:
                    if organization_id:
                        api_client.set_organization_context(organization_id)

                    api_client.update_workflow_execution_status(
                        execution_id=execution_id,
                        status=ExecutionStatus.ERROR.value,
                        error_message=str(e),
                    )
            except Exception as update_error:
                logger.error(f"Failed to update execution status: {update_error}")

            raise


@app.task(bind=True)
@monitor_performance
@circuit_breaker(failure_threshold=5, recovery_timeout=60.0)
def webhook_notification_task(
    self, webhook_url: str, payload: dict[str, Any], organization_id: str = None
) -> dict[str, Any]:
    """Example webhook notification task with circuit breaker protection.

    Args:
        webhook_url: Webhook URL to send notification to
        payload: Payload to send
        organization_id: Organization context

    Returns:
        Task result
    """
    task_id = self.request.id

    with log_context(task_id=task_id, organization_id=organization_id):
        logger.info(f"Sending webhook notification to {webhook_url}")

        try:
            # Initialize API client
            with InternalAPIClient(config) as api_client:
                if organization_id:
                    api_client.set_organization_context(organization_id)

                # Send webhook via internal API
                response = api_client.send_webhook(
                    url=webhook_url, payload=payload, timeout=30, max_retries=3
                )

                webhook_task_id = response.get("task_id")
                logger.info(f"Webhook queued with task ID: {webhook_task_id}")

                # Optionally wait for and check webhook status
                time.sleep(1)  # Brief wait
                status_response = api_client.get_webhook_status(webhook_task_id)

                logger.info(
                    f"Webhook notification completed: {status_response.get('status')}"
                )

                return {
                    "status": "success",
                    "webhook_task_id": webhook_task_id,
                    "webhook_status": status_response.get("status"),
                    "task_id": task_id,
                }

        except Exception as e:
            logger.error(f"Webhook notification task failed: {e}")
            raise


# Resilient executor example
resilient_executor = ResilientExecutor()


@app.task(bind=True)
@resilient_executor
def resilient_task(self, data: dict[str, Any]) -> dict[str, Any]:
    """Example task with both retry logic and circuit breaker protection.

    Args:
        data: Task data

    Returns:
        Task result
    """
    task_id = self.request.id

    with log_context(task_id=task_id):
        logger.info(f"Processing resilient task with data: {data}")

        # Simulate potential failure
        if data.get("simulate_failure"):
            raise Exception("Simulated failure for testing")

        # Simulate processing
        time.sleep(1)

        return {"status": "success", "task_id": task_id, "processed_data": data}


if __name__ == "__main__":
    """Run worker directly for testing."""
    logger.info("Starting example worker...")

    try:
        # Run health check
        health_report = health_checker.run_all_checks()
        logger.info(f"Initial health status: {health_report['status']}")

        # Start Celery worker
        app.start()

    except KeyboardInterrupt:
        logger.info("Worker shutdown requested")
    except Exception as e:
        logger.error(f"Worker failed to start: {e}")
    finally:
        health_server.stop()
        logger.info("Example worker stopped")
