import logging
import os
import signal
import threading
import time
from typing import Any

import redis
import socketio
from django.conf import settings
from django.core.wsgi import WSGIHandler

logger = logging.getLogger(__name__)
# shutdown = False

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
def connect(sid: str, environ: Any, auth: Any) -> None:
    logger.info(f"[{os.getpid()}] Client with SID:{sid} connected")
    # TODO Authenticate websocket connections
    # with sio.session(sid) as session:
        # session['authenticated'] = True

@sio.event
def disconnect(sid: str) -> None:
    logger.info(f"[{os.getpid()}] Client with SID:{sid} disconnected")


def _handle_pubsub_messages(message: Any) -> None:
    channel = message["channel"].decode("utf-8")
    data = message["data"]
    payload = {"data": data}

    logger.debug(f"[{os.getpid()}] Push websocket event: {channel}, {payload}")
    sio.emit(channel, {"data": data})


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

            # if shutdown:
            #     logger.info(f"[{os.getpid()}] Stopping to listen for pub sub messages...")
            #     pubsub.unsubscribe()
            #     break

            time.sleep(0.001)
    except Exception as e:
        logger.error(f"[{os.getpid()}] Failed to do pubsub: {e}")

# TODO Add graceful shutdown
# def _graceful_shutdown(signum, frame):
#     global shutdown
#     shutdown = True
#     # TODO Shutdown socketio server
#     # sio.close_room("logs:*", namespace="/")

def start_server(django_app: WSGIHandler, namespace: str) -> WSGIHandler:
    # signal.signal(signal.SIGINT, _graceful_shutdown)
    # signal.signal(signal.SIGTERM, _graceful_shutdown)

    django_app = socketio.WSGIApp(sio, django_app, socketio_path=namespace)

    pubsub_listener = threading.Thread(
        target=_pubsub_listen_forever, daemon=True
    )
    pubsub_listener.start()

    return django_app
