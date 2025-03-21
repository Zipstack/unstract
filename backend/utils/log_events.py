import http
import json
import logging
import os
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
    # Make sure only the web app origin and other explicitly added
    # CORS_ALLOWED_ORIGINS are allowed to create socket connection
    # TODO: this is a temporary fix we should refactor `CORS_ALLOWED_ORIGINS`
    # in to base to include settings.WEB_APP_ORIGIN_URL alone.
    cors_allowed_origins=(settings.CORS_ALLOWED_ORIGINS or [])
    + [settings.WEB_APP_ORIGIN_URL],
    logger=False,
    engineio_logger=False,
    always_connect=True,
    client_manager=socketio.KombuManager(url=settings.SOCKET_IO_MANAGER_URL),
)

redis_conn = redis.Redis(
    host=settings.REDIS_HOST,
    port=int(settings.REDIS_PORT),
    username=settings.REDIS_USER,
    password=settings.REDIS_PASSWORD,
)


@sio.event
def connect(sid: str, environ: Any, auth: Any) -> None:
    """This function is called when a client connects to the server.

    It handles the connection and authentication of the client.
    """
    logger.info(f"[{os.getpid()}] Client with SID:{sid} connected")
    session_id = _get_user_session_id_from_cookies(sid, environ)
    if session_id:
        sio.enter_room(sid, session_id)
        logger.info(f"Entered room {session_id} for socket {sid}")
    else:
        sio.disconnect(sid)


@sio.event
def disconnect(sid: str) -> None:
    logger.info(f"[{os.getpid()}] Client with SID:{sid} disconnected")


def _get_user_session_id_from_cookies(sid: str, environ: Any) -> Optional[str]:
    """Get the user session ID from cookies.

    Args:
        sid (str): The socket ID of the client.
        environ (Any): The environment variables of the client.

    Returns:
        Optional[str]: The user session ID.
    """
    cookie_str = environ.get("HTTP_COOKIE")
    if not cookie_str:
        logger.warning(f"No cookies found in {environ} for the sid {sid}")
        return None

    cookie = http.cookies.SimpleCookie(cookie_str)
    session_id = cookie.get(settings.SESSION_COOKIE_NAME)

    if not session_id:
        logger.warning(f"No session ID found in cookies for SID {sid}")
        return None

    return session_id.value


def _get_validated_log_data(json_data: Any) -> Optional[LogDataDTO]:
    """Validate log data to persist history. This function takes log data in
    JSON format, validates it, and returns a `LogDataDTO` object if the data is
    valid. The validation process includes decoding bytes to string, parsing
    the string as JSON, and checking for required fields and log type.

    Args:
        json_data (Any): Log data in JSON format
    Returns:
        Optional[LogDataDTO]: Log data DTO object
    """
    if isinstance(json_data, bytes):
        json_data = json_data.decode("utf-8")

    if isinstance(json_data, str):
        try:
            # Parse the string as JSON
            json_data = json.loads(json_data)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON data while validating {json_data}")
            return

    if not isinstance(json_data, dict):
        logger.warning(f"Getting invalid data type while validating {json_data}")
        return

    # Extract required fields from the JSON data
    execution_id = json_data.get(LogFieldName.EXECUTION_ID)
    organization_id = json_data.get(LogFieldName.ORGANIZATION_ID)
    timestamp = json_data.get(LogFieldName.TIMESTAMP)
    log_type = json_data.get(LogFieldName.TYPE)
    file_execution_id = json_data.get(LogFieldName.FILE_EXECUTION_ID)

    # Ensure the log type is LogType.LOG
    if log_type != LogType.LOG.value:
        return

    # Check if all required fields are present
    if not all((execution_id, organization_id, timestamp)):
        logger.debug(f"Missing required fields while validating {json_data}")
        return

    return LogDataDTO(
        execution_id=execution_id,
        file_execution_id=file_execution_id,
        organization_id=organization_id,
        timestamp=timestamp,
        log_type=log_type,
        data=json_data,
    )


def _store_execution_log(data: dict[str, Any]) -> None:
    """Store execution log in database
    Args:
        data (dict[str, Any]): Execution log data
    """
    if not ExecutionLogConstants.IS_ENABLED:
        return
    try:
        log_data = _get_validated_log_data(json_data=data)
        if log_data:
            redis_conn.rpush(ExecutionLogConstants.LOG_QUEUE_NAME, log_data.to_json())
    except Exception as e:
        logger.error(f"Error storing execution log: {e}")


def _emit_websocket_event(room: str, event: str, data: dict[str, Any]) -> None:
    """Emit websocket event
    Args:
        room (str): Room to emit event to
        event (str): Event name
        channel (str): Channel name
        data (bytes): Data to emit
    """
    payload = {"data": data}
    try:
        logger.debug(f"[{os.getpid()}] Push websocket event: {event}, {payload}")
        sio.emit(event, data=payload, room=room)
    except Exception as e:
        logger.error(f"Error emitting WebSocket event: {e}")


def handle_user_logs(room: str, event: str, message: dict[str, Any]) -> None:
    """Handle user logs from applications
    Args:
        message (dict[str, Any]): log message
    """

    if not room or not event:
        logger.warning(f"Message received without room and event: {message}")
        return

    _store_execution_log(message)
    _emit_websocket_event(room, event, message)


def start_server(django_app: WSGIHandler, namespace: str) -> WSGIHandler:
    django_app = socketio.WSGIApp(sio, django_app, socketio_path=namespace)
    return django_app
