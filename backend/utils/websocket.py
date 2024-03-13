import logging
import threading
from typing import Any
import os

import redis
import socketio
from django.conf import settings

logger = logging.getLogger(__name__)

sio = socketio.Server(
    # Allowed values: {threading, eventlet, gevent, gevent_uwsgi}
    async_mode="threading",
    cors_allowed_origins=["http://frontend.unstract.localhost"],
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
def connect(sid: str, environ: Any) -> None:
    logger.info(f"[{os.getpid()}] Client with SID:{sid} connected")


@sio.event
def disconnect(sid: str) -> None:
    logger.info(f"[{os.getpid()}] Client with SID:{sid} disconnected")


def _handle_pub_sub_messages(message: Any) -> None:
    channel = message["channel"].decode("utf-8")
    data = message["data"]

    payload = {"data": data}
    logger.info(f"[{os.getpid()}] Push websocket event: {channel}, {payload}")
    sio.emit(channel, {"data": data})


def _pubsub_listen_forever() -> None:
    try:
        pub_sub = redis_conn.pubsub(ignore_subscribe_messages=True)
        pub_sub.psubscribe("logs:*")
        logger.info(f"[{os.getpid()}] Listening for pub sub messages...")

        for message in pub_sub.listen():
            logger.info(f"[{os.getpid()}] Pub sub message received: {message}")  # type: ignore
            if message["type"] == "pmessage":
                _handle_pub_sub_messages(message)
    except Exception as e:
        logger.error(f"[{os.getpid()}] Failed to do pubsub: {e}")


def start_server(django_app, namespace:str):
    django_app = socketio.WSGIApp(sio, django_app, socketio_path=namespace)

    pub_sub_listener = threading.Thread(
        target=_pubsub_listen_forever, daemon=True
    )
    pub_sub_listener.start()

    return django_app
