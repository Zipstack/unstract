import http
import logging
import os
from typing import Any

import redis
import socketio
from django.conf import settings
from django.core.wsgi import WSGIHandler

from unstract.core.data_models import LogDataDTO
from unstract.core.log_utils import get_validated_log_data, store_execution_log
from utils.constants import ExecutionLogConstants

logger = logging.getLogger(__name__)

sio = socketio.Server(
    # Allowed values: {threading, eventlet, gevent, gevent_uwsgi}
    async_mode="threading",
    cors_allowed_origins=settings.CORS_ALLOWED_ORIGINS,
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


def _get_user_session_id_from_cookies(sid: str, environ: Any) -> str | None:
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


# Functions moved to unstract.core.log_utils for sharing with workers
# Keep these as wrapper functions for backward compatibility


def _get_validated_log_data(json_data: Any) -> LogDataDTO | None:
    """Validate log data to persist history (backward compatibility wrapper)."""
    return get_validated_log_data(json_data)


def _store_execution_log(data: dict[str, Any]) -> None:
    """Store execution log in database (backward compatibility wrapper)."""
    store_execution_log(
        data=data,
        redis_client=redis_conn,
        log_queue_name=ExecutionLogConstants.LOG_QUEUE_NAME,
        is_enabled=ExecutionLogConstants.IS_ENABLED,
    )


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
