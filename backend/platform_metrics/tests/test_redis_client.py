"""The metrics Redis pool: same target as the shared one, bounded waits."""

import socket
import threading
import time

import pytest
import redis
from redis.sentinel import Sentinel, SentinelConnectionPool

from platform_metrics.cache import with_timeouts


def test_copies_a_plain_pool_and_adds_timeouts():
    shared = redis.Redis(host="redis.internal", port=6380, db=3, password="pw")

    bounded = with_timeouts(shared, 1.5)

    kwargs = bounded.connection_pool.connection_kwargs
    assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("redis.internal", 6380, 3)
    assert kwargs["password"] == "pw"
    assert kwargs["socket_timeout"] == 1.5
    assert kwargs["socket_connect_timeout"] == 1.5
    assert bounded.connection_pool is not shared.connection_pool
    assert shared.connection_pool.connection_kwargs.get("socket_timeout") is None, (
        "the shared pool is left alone"
    )


def test_copies_a_sentinel_pool_and_adds_timeouts():
    sentinel = Sentinel(
        [("sentinel-a.internal", 26379), ("sentinel-b.internal", 26380)],
        min_other_sentinels=1,
        sentinel_kwargs={"password": "spw"},
    )
    shared = sentinel.master_for("mymaster", db=2, password="pw")

    bounded = with_timeouts(shared, 1.5)

    pool = bounded.connection_pool
    assert isinstance(pool, SentinelConnectionPool)
    assert pool.service_name == "mymaster"
    manager = pool.sentinel_manager
    assert manager is not sentinel, "discovery gets its own, bounded clients"
    assert manager.min_other_sentinels == 1
    discovery = [s.connection_pool.connection_kwargs for s in manager.sentinels]
    assert [(k["host"], k["port"]) for k in discovery] == [
        ("sentinel-a.internal", 26379),
        ("sentinel-b.internal", 26380),
    ]
    assert all(k["password"] == "spw" for k in discovery)
    assert all(k["socket_timeout"] == 1.5 for k in discovery)
    assert all(k["socket_connect_timeout"] == 1.5 for k in discovery)
    assert sentinel.sentinels[0].connection_pool.connection_kwargs.get(
        "socket_timeout"
    ) is None, "the shared sentinels are left alone"
    assert pool.connection_kwargs["db"] == 2
    assert pool.connection_kwargs["socket_timeout"] == 1.5
    assert pool.connection_kwargs["connection_pool"] is pool.proxy, (
        "the new pool points at itself, not at the shared one"
    )


@pytest.fixture
def stalled_redis():
    """A server that accepts connections and never replies."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    held = []
    stop = threading.Event()

    def accept():
        server.settimeout(0.1)
        while not stop.is_set():
            try:
                held.append(server.accept()[0])
            except OSError:
                pass

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    yield server.getsockname()[1]
    stop.set()
    thread.join()
    for conn in held:
        conn.close()
    server.close()


def test_a_stalled_redis_fails_within_the_timeout(stalled_redis):
    bounded = with_timeouts(redis.Redis(host="127.0.0.1", port=stalled_redis), 0.3)

    started = time.monotonic()
    with pytest.raises(redis.TimeoutError):
        bounded.get("anything")

    assert time.monotonic() - started < 2


def test_a_stalled_sentinel_fails_within_the_timeout(stalled_redis):
    shared = Sentinel([("127.0.0.1", stalled_redis)]).master_for("mymaster")
    bounded = with_timeouts(shared, 0.3)

    started = time.monotonic()
    with pytest.raises(redis.RedisError):
        bounded.get("anything")

    assert time.monotonic() - started < 2
