"""Sockets are tracked per session so ending a session can disconnect them.

A worker can list only its own sockets, so the ids live in a shared Redis set
and the disconnect goes through the Socket.IO manager, which forwards it to the
worker holding the socket.
"""

from unittest.mock import call, patch

from django.conf import settings
from django.test import SimpleTestCase

from utils import log_events

SESSION = "a" * 32


class _FakeRedis:
    def __init__(self) -> None:
        self.sets: dict[str, set[bytes]] = {}
        self.ttls: dict[str, int] = {}

    def sadd(self, key: str, member: str) -> None:
        self.sets.setdefault(key, set()).add(member.encode())

    def srem(self, key: str, member: str) -> None:
        self.sets.get(key, set()).discard(member.encode())

    def smembers(self, key: str) -> set[bytes]:
        return set(self.sets.get(key, set()))

    def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    def delete(self, key: str) -> None:
        self.sets.pop(key, None)


class SessionSocketsTest(SimpleTestCase):
    def setUp(self) -> None:
        self.redis = _FakeRedis()
        self.socket_sessions: dict[str, dict] = {}
        for target, kwargs in (
            ("_get_redis_conn", {"return_value": self.redis}),
            ("_get_user_id", {"return_value": None}),
        ):
            patcher = patch.object(log_events, target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, side_effect in (
            ("save_session", self.socket_sessions.__setitem__),
            ("get_session", self.socket_sessions.__getitem__),
        ):
            patcher = patch.object(log_events.sio, name, side_effect=side_effect)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ("enter_room", "disconnect"):
            patcher = patch.object(log_events.sio, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def _connect(self, sid: str) -> None:
        environ = {"HTTP_COOKIE": f"{settings.SESSION_COOKIE_NAME}={SESSION}"}
        log_events.connect(sid, environ, None)

    def test_connected_sockets_are_tracked_for_their_session(self) -> None:
        self._connect("sid-1")
        self._connect("sid-2")

        key = f"session_sockets:{SESSION}"
        self.assertEqual(self.redis.smembers(key), {b"sid-1", b"sid-2"})
        self.assertEqual(self.redis.ttls[key], settings.SESSION_COOKIE_AGE)

    def test_a_disconnected_socket_is_untracked(self) -> None:
        self._connect("sid-1")
        self._connect("sid-2")

        log_events.disconnect("sid-1")

        self.assertEqual(self.redis.smembers(f"session_sockets:{SESSION}"), {b"sid-2"})

    def test_ending_a_session_disconnects_each_of_its_sockets(self) -> None:
        self._connect("sid-1")
        self._connect("sid-2")

        log_events.disconnect_session_sockets(SESSION)

        self.disconnect.assert_has_calls([call("sid-1"), call("sid-2")], any_order=True)
        self.assertEqual(self.redis.smembers(f"session_sockets:{SESSION}"), set())

    def test_tracking_failure_does_not_block_the_connection(self) -> None:
        with patch.object(
            log_events, "_get_redis_conn", side_effect=ConnectionError("redis down")
        ):
            self._connect("sid-1")

        self.enter_room.assert_called_with("sid-1", SESSION)
