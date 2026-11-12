"""Sockets are tracked per session so ending a session can disconnect them.

A worker can list only its own sockets, so the ids live in a shared Redis set
and the disconnect goes through the Socket.IO manager, which forwards it to the
worker holding the socket.
"""

# The fake's `set` method would otherwise shadow the builtin in its annotations.
from __future__ import annotations

from unittest.mock import call, patch

from django.conf import settings
from django.test import SimpleTestCase

from utils import log_events

SESSION = "a" * 32


class _FakeRedis:
    def __init__(self) -> None:
        self.sets: dict[str, set[bytes]] = {}
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value.encode()
        self.ttls[key] = ex

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def sadd(self, key: str, member: str) -> None:
        self.sets.setdefault(key, set()).add(member.encode())

    def srem(self, key: str, member: str) -> None:
        self.sets.get(key, set()).discard(member.encode())

    def smembers(self, key: str) -> set[bytes]:
        return set(self.sets.get(key, set()))

    def expire(self, key: str, seconds: int) -> bool:
        if key not in self.sets and key not in self.values:
            return False
        self.ttls[key] = seconds
        return True

    def delete(self, key: str) -> None:
        self.sets.pop(key, None)
        self.values.pop(key, None)


class SessionSocketsTest(SimpleTestCase):
    def setUp(self) -> None:
        self.redis = _FakeRedis()
        for target, kwargs in (
            ("_get_redis_conn", {"return_value": self.redis}),
            ("_get_user_id", {"return_value": None}),
        ):
            patcher = patch.object(log_events, target, **kwargs)
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
        self.assertEqual(
            self.redis.ttls["socket_session:sid-1"], settings.SESSION_COOKIE_AGE
        )

    def test_renewal_extends_the_session_and_socket_tracking(self) -> None:
        self._connect("sid-1")

        log_events.renew_session_sockets(SESSION, ttl=999)

        self.assertEqual(self.redis.ttls[f"session_sockets:{SESSION}"], 999)
        self.assertEqual(self.redis.ttls["socket_session:sid-1"], 999)

    def test_renewal_of_an_untracked_session_creates_nothing(self) -> None:
        log_events.renew_session_sockets(SESSION, ttl=999)

        self.assertEqual(self.redis.ttls, {})

    def test_a_disconnected_socket_is_untracked(self) -> None:
        self._connect("sid-1")
        self._connect("sid-2")

        log_events.disconnect("sid-1")

        self.assertEqual(self.redis.smembers(f"session_sockets:{SESSION}"), {b"sid-2"})
        self.assertIsNone(self.redis.get("socket_session:sid-1"))

    def test_ending_a_session_disconnects_each_of_its_sockets(self) -> None:
        self._connect("sid-1")
        self._connect("sid-2")

        log_events.disconnect_session_sockets(SESSION)

        self.disconnect.assert_has_calls([call("sid-1"), call("sid-2")], any_order=True)
        self.assertEqual(self.redis.smembers(f"session_sockets:{SESSION}"), set())

    def test_a_socket_whose_session_ends_while_joining_leaves_the_user_room(
        self,
    ) -> None:
        with (
            patch.object(log_events, "_get_user_id", side_effect=["5", None]),
            patch.object(log_events.sio, "leave_room") as leave_room,
        ):
            self._connect("sid-1")

        self.enter_room.assert_any_call("sid-1", "user:5")
        leave_room.assert_called_once_with("sid-1", "user:5")

    def test_a_socket_whose_session_stays_valid_keeps_the_user_room(self) -> None:
        with (
            patch.object(log_events, "_get_user_id", return_value="5"),
            patch.object(log_events.sio, "leave_room") as leave_room,
        ):
            self._connect("sid-1")

        self.enter_room.assert_any_call("sid-1", "user:5")
        leave_room.assert_not_called()

    def test_a_socket_that_cannot_be_tracked_is_refused(self) -> None:
        # Ending its session could not reach it, so it must join no room.
        with patch.object(
            log_events, "_get_redis_conn", side_effect=ConnectionError("redis down")
        ):
            self._connect("sid-1")

        self.enter_room.assert_not_called()
        self.disconnect.assert_called_once_with("sid-1")
