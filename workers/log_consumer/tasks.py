"""Log Consumer Tasks

This module contains Celery tasks for processing execution logs.
"""

import os
from typing import Any

from celery import shared_task
from shared.api_client_singleton import get_singleton_api_client
from shared.config import WorkerConfig
from shared.logging_utils import WorkerLogger

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
def log_consumer(**kwargs: Any) -> None:
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
