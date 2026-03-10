"""Log Consumer Tasks

This module contains Celery tasks for processing execution logs.
"""

import os
from typing import Any
from urllib.parse import quote

import socketio
from celery import shared_task
from shared.infrastructure.config import WorkerConfig
from shared.infrastructure.logging import WorkerLogger
from shared.utils.api_client_singleton import get_singleton_api_client

from unstract.core.cache.redis_queue_client import RedisQueueClient
from unstract.core.constants import LogEventArgument, LogProcessingTask
from unstract.core.log_utils import store_execution_log

logger = WorkerLogger.get_logger(__name__)

# Initialize worker configuration
config = WorkerConfig.from_env("LOG_CONSUMER")

# Redis configuration
redis_client = RedisQueueClient.from_env()

# Log storage configuration
log_queue_name = os.getenv("LOG_HISTORY_QUEUE_NAME", "log_history_queue")
log_storage_enabled = os.getenv("ENABLE_LOG_HISTORY", "true").lower() == "true"

# Socket.IO client for emitting events (uses same KombuManager as backend)
_sentinel_mode = os.getenv("REDIS_SENTINEL_MODE", "False").strip().lower() == "true"
_redis_host = os.getenv("REDIS_HOST", "localhost")
_redis_port = os.getenv("REDIS_PORT", "6379")
_transport_options: dict[str, Any] = {}
if _sentinel_mode:
    _redis_password = os.getenv("REDIS_PASSWORD", "")
    _redis_user = os.getenv("REDIS_USER", "")
    _redis_db = os.getenv("REDIS_DB", "0") or "0"
    _cred_prefix = ""
    if _redis_user and _redis_password:
        _cred_prefix = f"{quote(_redis_user, safe='')}:{quote(_redis_password, safe='')}@"
    elif _redis_password:
        _cred_prefix = f":{quote(_redis_password, safe='')}@"
    socket_io_manager_url = (
        f"sentinel://{_cred_prefix}{_redis_host}:{_redis_port}/{_redis_db}"
    )
    _transport_options = {"master_name": "mymaster"}
else:
    socket_io_manager_url = f"redis://{_redis_host}:{_redis_port}"

sio = socketio.Server(
    async_mode="threading",
    logger=False,
    engineio_logger=False,
    client_manager=socketio.KombuManager(
        url=socket_io_manager_url,
        write_only=True,
        **({"transport_options": _transport_options} if _transport_options else {}),
    ),
)


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
            redis_client=redis_client.redis_client,
            log_queue_name=log_queue_name,
            is_enabled=log_storage_enabled,
        )
    except Exception as e:
        logger.error(f"Failed to store execution log: {e}")

    # Emit WebSocket event directly through Socket.IO (via Redis broker)
    try:
        payload = {"data": log_message}
        sio.emit(event, data=payload, room=room)
        logger.debug(f"WebSocket event emitted successfully for room {room}")
    except Exception as e:
        logger.error(f"Failed to emit WebSocket event: {e}")


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
