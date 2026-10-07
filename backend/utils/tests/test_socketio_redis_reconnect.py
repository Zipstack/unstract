"""Regression test: the Socket.IO pub/sub listener must survive a Redis restart.

log_events.py wires ``socketio.Server`` to Redis through ``KombuManager``. Each
backend process runs one listener thread that relays events published by
other processes (e.g. the pod that handled ``/internal/emit-websocket/``) to
the browsers connected to it. python-socketio 5.9.0 retried only on
``OSError`` and ``KombuError``, so the ``redis.exceptions.ConnectionError``
raised when Redis restarts killed that thread for the life of the process:
the pod kept accepting sockets but never delivered another event, and Prompt
Studio results showed only after a manual refresh.

The fix is the dependency floor (5.16.3+ retries on any exception). This test
pins that behaviour so a downgrade cannot silently reopen the gap.
"""

from __future__ import annotations

from unittest import mock

import redis
import socketio


class _Message:
    def __init__(self, payload):
        self.payload = payload

    def ack(self):
        pass


class _Queue:
    def __init__(self, items):
        self._items = list(items)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, block=True):
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Connection:
    def __init__(self, queue):
        self._queue = queue

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def SimpleQueue(self, reader_queue):  # noqa: N802 - kombu's API name
        return self._queue


def test_listener_reconnects_after_redis_connection_error():
    manager = socketio.KombuManager(url="redis://localhost:6379/0", write_only=True)
    payload = {"method": "emit", "event": "prompt_studio_result"}
    connections = [
        # First connection: Redis goes away mid-read, as on a restart.
        _Connection(
            _Queue([redis.exceptions.ConnectionError("Connection closed by server.")])
        ),
        # Second connection: Redis is back and the next event arrives.
        _Connection(_Queue([_Message(payload)])),
    ]

    with (
        mock.patch.object(manager, "_queue", return_value=object()),
        mock.patch.object(manager, "_connection", side_effect=connections),
        mock.patch("socketio.kombu_manager.time.sleep"),
    ):
        listener = manager._listen()
        assert next(listener) == payload
