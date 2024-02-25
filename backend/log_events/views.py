import logging
import threading
from typing import Any

import redis
import socketio
from django.conf import settings

logger = logging.getLogger(__name__)

# Set async_mode to 'threading', 'eventlet', 'gevent' or 'gevent_uwsgi' to
# force a mode else, the best mode is selected automatically from what's
# installed.
# Enable socketio logger if needed
# engineio_logger=True,
sio = socketio.Server(
    async_mode="threading",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
    always_connect=True,
    ping_timeout=300,  # We need to decide and finalize the value
)

redis_conn = redis.Redis(
    host=settings.REDIS_HOST,
    port=int(settings.REDIS_PORT),
    username=settings.REDIS_USER,
    password=settings.REDIS_PASSWORD,
)


@sio.event
def connect(sid: str, environ: Any) -> None:
    logger.info(f"Client with SID:{sid} connected")


@sio.event
def disconnect(sid: str) -> None:
    logger.info(f"Client with--------------------Client SID:{sid} disconnected")


def handle_pub_sub_messages(message: Any) -> None:
    channel = message["channel"].decode("utf-8")
    data = message["data"]
    sio.emit(channel, {"data": data})


def background_task_for_pub_sub() -> None:
    channel_pattern = "logs:*"
    try:
        # Subscribe to the Redis Pub/Sub channel
        pubsub = redis_conn.pubsub(ignore_subscribe_messages=True)
        pubsub.psubscribe(channel_pattern)

        # Start listening for messages from Redis
        for message in pubsub.listen():  # type: ignore
            if message["type"] == "pmessage":
                handle_pub_sub_messages(message)
    except Exception as e:
        logger.error(f"Error occured in background task to pubsub::{e}")


background_thread = threading.Thread(
    target=background_task_for_pub_sub, daemon=True
)
background_thread.start()
