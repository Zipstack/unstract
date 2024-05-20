import json
import logging
import os
import threading
import time
from typing import Any, Optional

import redis
import socketio
from django.conf import settings
from django.core.wsgi import WSGIHandler
from unstract.workflow_execution.enums import LogType
from utils.constants import ExecutionLogConstants
from utils.dto import LogDataDTO

from unstract.core.constants import LogFieldName

logger = logging.getLogger(__name__)

sio = socketio.Server(
    # Allowed values: {threading, eventlet, gevent, gevent_uwsgi}
    async_mode="threading",
    cors_allowed_origins=settings.CORS_ALLOWED_ORIGINS,
    logger=False,
    engineio_logger=False,
    always_connect=True,
)
redis_conn = redis.Redis(
    host=settings.REDIS_HOST,
    port=int(settings.REDIS_PORT),
    username=settings.REDIS_USER,
    password=settings.REDIS_PASSWORD,
)


@sio.event
def connect(sid: str, environ: Any, auth: Any) -> None:
    # TODO Authenticate websocket connections
    logger.info(f"[{os.getpid()}] Client with SID:{sid} connected")


@sio.event
def disconnect(sid: str) -> None:
    logger.info(f"[{os.getpid()}] Client with SID:{sid} disconnected")


def _get_validated_log_data(json_data: Any) -> Optional[LogDataDTO]:
    """Validate log data to persist history
    Args:
        json_data (Any): Log data in JSON format
    """
    if isinstance(json_data, bytes):
        json_data = json_data.decode("utf-8")

    if isinstance(json_data, str):
        try:
            # Parse the string as JSON
            json_data = json.loads(json_data)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON data {json_data}")
            return

    if not isinstance(json_data, dict):
        return

    # Extract required fields from the JSON data
    execution_id = json_data.get(LogFieldName.EXECUTION_ID)
    organization_id = json_data.get(LogFieldName.ORGANIZATION_ID)
    timestamp = json_data.get(LogFieldName.TIMESTAMP)
    log_type = json_data.get(LogFieldName.TYPE)

    # Check if all required fields are present
    if not all((execution_id, organization_id, timestamp, log_type)):
        return

    # Ensure the log type is LogType.LOG
    if log_type != LogType.LOG.value:
        return

    return LogDataDTO(
        execution_id=execution_id,
        organization_id=organization_id,
        timestamp=timestamp,
        log_type=log_type,
        data=json_data,
    )


def _store_execution_log(data: bytes) -> None:
    """Store execution log in database
    Args:
        data (bytes): Execution log data in bytes format
    """
    if not ExecutionLogConstants.IS_ENABLED:
        return
    try:
        log_data = _get_validated_log_data(json_data=data)
        if log_data:
            redis_conn.rpush(ExecutionLogConstants.LOG_QUEUE_NAME, log_data.to_json())
    except Exception as e:
        logger.error(f"Error storing execution log: {e}")


def _emit_websocket_event(channel: str, data: bytes) -> None:
    """Emit websocket event
    Args:
        channel (str): WebSocket channel
        data (bytes): Execution log data in bytes format
    """
    payload = {"data": data}
    try:
        logger.debug(f"[{os.getpid()}] Push websocket event: {channel}, {payload}")
        sio.emit(channel, payload)
    except Exception as e:
        logger.error(f"Error emitting WebSocket event: {e}")


def _handle_pubsub_messages(message: dict[str, Any]) -> None:
    """Handle pubsub messages
    Args:
        message (dict[str, Any]): Pub sub message
    """
    channel = message.get("channel")
    data = message.get("data")

    if not channel or not data:
        logger.warning(f"Invalid message received: {message}")
        return

    try:
        channel_str = channel.decode("utf-8")
    except UnicodeDecodeError as e:
        logger.error(f"Error decoding channel: {e}")
        return

    _store_execution_log(data)
    _emit_websocket_event(channel_str, data)


def _pubsub_listen_forever() -> None:
    global shutdown

    try:
        pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
        pubsub.psubscribe("logs:*")

        logger.info(f"[{os.getpid()}] Listening for pub sub messages...")
        while True:
            message = pubsub.get_message()

            if message:
                logger.debug(f"[{os.getpid()}] Pub sub message received: {message}")
                if message["type"] == "pmessage":
                    _handle_pubsub_messages(message)

            # TODO Add graceful shutdown

            time.sleep(0.01)
    except Exception as e:
        logger.error(f"[{os.getpid()}] Failed to do pubsub: {e}")


def start_server(django_app: WSGIHandler, namespace: str) -> WSGIHandler:
    django_app = socketio.WSGIApp(sio, django_app, socketio_path=namespace)

    pubsub_listener = threading.Thread(target=_pubsub_listen_forever, daemon=True)
    pubsub_listener.start()

    return django_app
