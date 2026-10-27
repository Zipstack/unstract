"""SnapshotCache: Redis sharing, the refresh lock, and failure fallbacks."""

import json

import pytest
from django.test import override_settings

from platform_metrics.cache import RefreshFailed, SnapshotCache
from platform_metrics.tests.fakes import Clock, FakeRedis, StubGroup

DATA_KEY = "platform_metrics:v1:data:g"
LOCK_KEY = "platform_metrics:v1:lock:g"


@pytest.fixture(autouse=True)
def _ttl():
    with override_settings(PLATFORM_METRICS_CACHE_TTL_SECONDS=15):
        yield


@pytest.fixture
def redis():
    return FakeRedis()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def cache(redis, clock):
    return SnapshotCache(client_factory=lambda: redis, clock=clock)


def _seed(redis, value, refreshed_at):
    redis.data[DATA_KEY] = json.dumps(
        {"data": {"value": value}, "refreshed_at": refreshed_at}
    )


def test_first_scrape_fetches_and_shares_through_redis(cache, redis, clock):
    group = StubGroup("g", value=7)

    snapshot = cache.resolve(group)

    assert snapshot.data == {"value": 7}
    assert snapshot.refreshed_at == clock.now
    assert group.fetches == 1
    assert json.loads(redis.data[DATA_KEY])["data"] == {"value": 7}
    # Kept well past the TTL: it is the stale fallback while refreshes fail.
    assert redis.expiry[DATA_KEY] > 15
    assert not redis.locks, "the lock must be released after the refresh"


def test_fresh_snapshot_is_served_without_touching_the_db(cache, redis, clock):
    _seed(redis, 3, clock.now - 5)
    group = StubGroup("g")

    assert cache.resolve(group).data == {"value": 3}
    assert group.fetches == 0


def test_snapshot_written_by_another_pod_is_reused(redis, clock):
    group = StubGroup("g")
    pod_a = SnapshotCache(client_factory=lambda: redis, clock=clock)
    pod_b = SnapshotCache(client_factory=lambda: redis, clock=clock)

    pod_a.resolve(group)
    pod_b.resolve(group)

    assert group.fetches == 1


def test_stale_snapshot_is_refreshed(cache, redis, clock):
    _seed(redis, 3, clock.now - 16)
    group = StubGroup("g", value=9)

    assert cache.resolve(group).data == {"value": 9}
    assert group.fetches == 1


def test_lock_held_elsewhere_serves_stale_without_fetching(cache, redis, clock):
    _seed(redis, 3, clock.now - 60)
    redis.locks.add(LOCK_KEY)
    group = StubGroup("g")

    snapshot = cache.resolve(group)

    assert snapshot.data == {"value": 3}
    assert group.fetches == 0


def test_lock_held_and_nothing_cached_leaves_the_group_out(cache, redis):
    redis.locks.add(LOCK_KEY)
    group = StubGroup("g")

    assert cache.resolve(group) is None
    assert group.fetches == 0


def test_refresh_failure_serves_last_snapshot(cache, redis, clock):
    _seed(redis, 3, clock.now - 60)
    group = StubGroup("g")
    group.error = RuntimeError("db down")

    with pytest.raises(RefreshFailed) as failed:
        cache.resolve(group)

    assert failed.value.snapshot.data == {"value": 3}
    assert not redis.locks
    # The stale value stays in Redis for the other pods.
    assert json.loads(redis.data[DATA_KEY])["data"] == {"value": 3}


def test_refresh_failure_with_nothing_cached_has_no_snapshot(cache):
    group = StubGroup("g")
    group.error = RuntimeError("db down")

    with pytest.raises(RefreshFailed) as failed:
        cache.resolve(group)

    assert failed.value.snapshot is None


def test_redis_down_refreshes_locally_at_most_once_per_ttl(cache, redis, clock):
    redis.down = True
    group = StubGroup("g", value=5)

    with pytest.raises(RefreshFailed) as first:
        cache.resolve(group)
    clock.now += 10
    with pytest.raises(RefreshFailed) as second:
        cache.resolve(group)

    assert first.value.snapshot.data == {"value": 5}
    assert second.value.snapshot.data == {"value": 5}
    assert group.fetches == 1, "DB load stays bounded per pod while Redis is down"

    clock.now += 10
    with pytest.raises(RefreshFailed):
        cache.resolve(group)
    assert group.fetches == 2


def test_redis_down_after_a_good_read_serves_the_local_copy(cache, redis, clock):
    _seed(redis, 3, clock.now)
    group = StubGroup("g")
    cache.resolve(group)
    redis.down = True

    with pytest.raises(RefreshFailed) as failed:
        cache.resolve(group)

    assert failed.value.snapshot.data == {"value": 3}
    assert group.fetches == 0


def test_redis_write_failure_still_serves_the_fresh_snapshot(cache, redis):
    group = StubGroup("g", value=4)

    def broken_set(*args, **kwargs):
        raise ConnectionError("write failed")

    redis.set = broken_set

    assert cache.resolve(group).data == {"value": 4}
    assert not redis.locks


def test_groups_are_cached_independently(cache, redis, clock):
    first, second = StubGroup("a"), StubGroup("b")

    cache.resolve(first)
    cache.resolve(second)
    cache.resolve(first)

    assert (first.fetches, second.fetches) == (1, 1)
    assert set(redis.data) == {
        "platform_metrics:v1:data:a",
        "platform_metrics:v1:data:b",
    }


def test_rechecks_redis_after_taking_the_lock(cache, redis, clock):
    """A pod that finished refreshing between our read and our acquire wins."""
    _seed(redis, 3, clock.now - 60)
    group = StubGroup("g")
    make_lock = redis.lock

    def lock_after_other_pod_refreshed(name, timeout=None):
        _seed(redis, 8, clock.now)
        return make_lock(name, timeout=timeout)

    redis.lock = lock_after_other_pod_refreshed

    assert cache.resolve(group).data == {"value": 8}
    assert group.fetches == 0
