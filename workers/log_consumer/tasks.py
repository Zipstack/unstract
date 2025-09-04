"""Log Consumer Tasks

This module contains Celery tasks for processing execution logs.
"""

import os
from collections import defaultdict
from typing import Any

from celery import shared_task
from shared.clients.log_client import LogAPIClient
from shared.infrastructure.config import WorkerConfig
from shared.infrastructure.logging import WorkerLogger
from shared.legacy.api_client_singleton import get_singleton_api_client

from unstract.core.constants import LogEventArgument, LogProcessingTask
from unstract.core.log_utils import create_redis_client, store_execution_log

logger = WorkerLogger.get_logger(__name__)

# Initialize worker configuration
config = WorkerConfig.from_env("LOG_CONSUMER")

# Redis configuration
redis_client = create_redis_client(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    username=os.getenv("REDIS_USER"),
    password=os.getenv("REDIS_PASSWORD"),
)

# Log storage configuration
log_queue_name = os.getenv("LOG_HISTORY_QUEUE_NAME", "log_history_queue")
log_storage_enabled = os.getenv("ENABLE_LOG_HISTORY", "true").lower() == "true"


@shared_task(name=LogProcessingTask.TASK_NAME)
def logs_consumer(**kwargs: Any) -> None:
    """Task to process logs from log publisher.

    This task processes execution logs by:
    1. Storing them to Redis queue for persistence
    2. Triggering WebSocket emission through backend API

    Args:
        kwargs: The arguments to process the logs.
        Expected arguments:
            USER_SESSION_ID: The room to be processed.
            EVENT: The event to be processed Ex: logs:{session_id}.
            MESSAGE: The message to be processed Ex: execution log.
    """
    log_message = kwargs.get(LogEventArgument.MESSAGE)
    room = kwargs.get(LogEventArgument.USER_SESSION_ID)
    event = kwargs.get(LogEventArgument.EVENT)

    logger.debug(f"[{os.getpid()}] Log message received: {log_message} for room {room}")

    # Validate required arguments
    if not room or not event:
        logger.warning(f"Message received without room and event: {log_message}")
        return

    # Store execution log to Redis
    try:
        store_execution_log(
            data=log_message,
            redis_client=redis_client,
            log_queue_name=log_queue_name,
            is_enabled=log_storage_enabled,
        )
    except Exception as e:
        logger.error(f"Failed to store execution log: {e}")

    # Emit WebSocket event through backend API
    try:
        _emit_websocket_via_api(room=room, event=event, data=log_message)
    except Exception as e:
        logger.error(f"Failed to emit WebSocket event: {e}")


def _emit_websocket_via_api(room: str, event: str, data: dict[str, Any]) -> None:
    """Emit WebSocket event via backend internal API.

    Args:
        room: Room to emit event to
        event: Event name
        data: Data to emit
    """
    try:
        import json
        from datetime import datetime
        from uuid import UUID

        import requests

        def serialize_for_json(obj):
            """Custom JSON serializer for UUID and datetime objects."""
            if isinstance(obj, UUID):
                return str(obj)
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: serialize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [serialize_for_json(item) for item in obj]
            return obj

        # Serialize data to handle UUIDs and datetimes
        serialized_data = serialize_for_json(data)

        # Prepare payload for internal API
        payload = {"room": room, "event": event, "data": serialized_data}

        # Create request headers (no organization validation needed for WebSocket emission)
        headers = {
            "Authorization": f"Bearer {config.internal_api_key}",
            "Content-Type": "application/json",
        }

        # Call internal API endpoint directly (bypasses organization validation)
        url = f"{config.internal_api_base_url.rstrip('/')}/emit-websocket/"

        # Manually serialize to JSON to ensure UUID handling
        json_data = json.dumps(
            payload,
            default=lambda o: str(o)
            if isinstance(o, UUID)
            else o.isoformat()
            if isinstance(o, datetime)
            else str(o),
        )

        response = requests.post(
            url=url, data=json_data, headers=headers, timeout=config.api_timeout
        )

        if response.status_code != 200:
            logger.warning(
                f"WebSocket emission API returned status {response.status_code}: {response.text}"
            )
        else:
            logger.debug(f"WebSocket event emitted successfully for room {room}")

    except Exception as e:
        logger.error(f"Error calling WebSocket emission API: {e}")


# Health check task for monitoring
@shared_task(name="log_consumer_health_check")
def health_check() -> dict[str, Any]:
    """Health check task for log consumer worker.

    Returns:
        Health status information
    """
    try:
        # Check Redis connectivity
        redis_client.ping()
        redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {e}"

    try:
        # Check API client connectivity
        api_client = get_singleton_api_client(config)
        api_status = "healthy" if api_client else "unhealthy"
    except Exception as e:
        api_status = f"unhealthy: {e}"

    return {
        "worker": "log_consumer",
        "status": "healthy"
        if redis_status == "healthy" and "healthy" in api_status
        else "degraded",
        "redis": redis_status,
        "api": api_status,
        "queue": log_queue_name,
        "log_storage_enabled": log_storage_enabled,
    }


# Constants for log history consumption (matching backend constants)
LOGS_BATCH_LIMIT = int(os.getenv("LOGS_BATCH_LIMIT", "100"))
LOG_HISTORY_QUEUE_NAME = os.getenv("LOG_HISTORY_QUEUE_NAME", "log_history_queue")


@shared_task(name="consume_log_history")
def consume_log_history() -> dict[str, Any]:
    """Task to consume log history from Redis queue and store to database via API.

    This task:
    1. Retrieves logs from Redis cache in batches
    2. Validates execution references via internal API
    3. Groups logs by organization
    4. Bulk creates execution logs via internal API

    Returns:
        Dictionary with processing results and statistics
    """
    try:
        # Initialize API client for log operations
        log_client = LogAPIClient(config)

        # Retrieve batch of logs from cache
        cache_response = log_client.get_cache_log_batch(
            queue_name=LOG_HISTORY_QUEUE_NAME, batch_limit=LOGS_BATCH_LIMIT
        )

        if not cache_response.success:
            logger.error(f"Failed to retrieve logs from cache: {cache_response.error}")
            return {
                "status": "error",
                "processed_count": 0,
                "message": cache_response.error,
            }

        logs_data = cache_response.data.get("logs", []) if cache_response.data else []

        if not logs_data:
            logger.debug("No logs found in history queue")
            return {
                "status": "success",
                "processed_count": 0,
                "message": "No logs to process",
            }

        logs_count = len(logs_data)
        logger.info(f"Processing {logs_count} logs from history queue")

        # Group logs for processing and validation
        organization_logs = defaultdict(list)
        execution_ids = set()
        file_execution_ids = set()

        # Parse and validate log data
        valid_logs = []
        for log_data in logs_data:
            # Validate required fields
            execution_id = log_data.get("execution_id")
            organization_id = log_data.get("organization_id")

            if not execution_id or not organization_id:
                logger.warning(f"Skipping log with missing required fields: {log_data}")
                continue

            execution_ids.add(execution_id)
            if log_data.get("file_execution_id"):
                file_execution_ids.add(log_data["file_execution_id"])

            valid_logs.append(log_data)

        if not valid_logs:
            logger.warning("No valid logs found in batch")
            return {
                "status": "warning",
                "processed_count": 0,
                "message": "No valid logs found",
            }

        # Validate execution references exist
        validation_response = log_client.validate_execution_references(
            execution_ids=list(execution_ids), file_execution_ids=list(file_execution_ids)
        )

        if not validation_response.success:
            logger.error(
                f"Failed to validate execution references: {validation_response.error}"
            )
            return {
                "status": "error",
                "processed_count": 0,
                "message": validation_response.error,
            }

        validation_data = validation_response.data or {}
        valid_execution_ids = validation_data.get("valid_executions", set())
        valid_file_execution_ids = validation_data.get("valid_file_executions", set())

        # Filter logs to only include those with valid execution references
        processed_logs = []
        skipped_count = 0

        for log_data in valid_logs:
            execution_id = log_data["execution_id"]
            file_execution_id = log_data.get("file_execution_id")

            # Skip logs with invalid execution references
            if execution_id not in valid_execution_ids:
                logger.warning(f"Skipping log with invalid execution_id: {execution_id}")
                skipped_count += 1
                continue

            # Skip logs with invalid file execution references
            if file_execution_id and file_execution_id not in valid_file_execution_ids:
                logger.warning(
                    f"Skipping log with invalid file_execution_id: {file_execution_id}"
                )
                skipped_count += 1
                continue

            processed_logs.append(log_data)
            organization_logs[log_data["organization_id"]].append(log_data)

        if not processed_logs:
            logger.warning("No logs with valid execution references found")
            return {
                "status": "warning",
                "processed_count": 0,
                "skipped_count": skipped_count,
                "message": "No logs with valid execution references",
            }

        # Bulk create logs via internal API
        total_created = 0
        errors = []

        for organization_id, org_logs in organization_logs.items():
            logger.info(
                f"Creating {len(org_logs)} logs for organization: {organization_id}"
            )

            try:
                bulk_response = log_client.create_execution_logs_bulk(org_logs)

                if not bulk_response.success:
                    errors.append(f"Org {organization_id}: {bulk_response.errors}")
                else:
                    created_count = bulk_response.successful_items
                    total_created += created_count

            except Exception as e:
                error_msg = (
                    f"Failed to create logs for organization {organization_id}: {e}"
                )
                logger.error(error_msg)
                errors.append(error_msg)

        # Prepare result summary
        result = {
            "status": "success" if not errors else "partial_success",
            "processed_count": total_created,
            "skipped_count": skipped_count,
            "total_logs": logs_count,
            "organizations_processed": len(organization_logs),
        }

        if errors:
            result["errors"] = errors
            result["error_count"] = len(errors)

        logger.info(f"Log history consumption completed: {result}")
        return result

    except Exception as e:
        error_msg = f"Failed to consume log history: {e}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "processed_count": 0, "message": error_msg}
