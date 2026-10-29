"""Shared, lock-guarded snapshot cache for the platform metric groups.

Every backend pod serves ``/metrics``, and Prometheus scrapes each of them, so
without coordination the DB would run every group's queries once per pod per
scrape. Instead each group's snapshot lives in Redis for
``PLATFORM_METRICS_CACHE_TTL_SECONDS`` (default 15s), and a non-blocking Redis
lock lets exactly one pod refresh a stale group while the others keep serving
the previous snapshot. DB cost is about one refresh per group per TTL however
many replicas there are.

Failure handling, per group and independent of the others:

* the refresh query fails: serve the last snapshot (Redis, else this
  process's copy) and count the failure. The refresh lock is then held for
  one TTL, so the DB is retried about once per TTL, not on every scrape;
* Redis is unreachable or stalls (its own pool has socket timeouts, and a
  failure skips Redis for a few seconds after, so a stall costs a scrape at
  most one timeout): fall back to this process's copy, refreshing it from
  the DB (successfully or not) at most once per TTL, so DB load stays bounded per gunicorn worker
  process rather than per scrape. The failure is counted;
* the Redis entry is unreadable (e.g. written by another version): treated as
  missing, so the next refresh overwrites it;
* nothing has ever been fetched (first scrape, while another pod holds the
  lock): the group is left out of this scrape.

Refresh failures are counted in Redis too (:class:`FailureCounter`), so every
pod and worker process reports the same monotonic total. A per-process counter
would jump between processes from scrape to scrape, which Prometheus reads as
counter resets.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings

from .groups import MetricGroup, Snapshot

logger = logging.getLogger(__name__)

_KEY_PREFIX = "platform_metrics:v1"
#: How long a snapshot stays in Redis. Far beyond the TTL on purpose: it is the
#: last-known-good value served while refreshes fail.
_RETENTION_SECONDS = 3600
#: Floor for the lock expiry. A pod that dies mid-refresh frees the group
#: within this long instead of wedging it.
_MIN_LOCK_TIMEOUT_SECONDS = 30


def _lock_timeout_seconds(group: MetricGroup) -> float:
    """Lock expiry, kept above the longest refresh the statement timeout allows.

    The timeout bounds each statement, so a group's refresh can take its
    statement count times that. A shorter lock could expire mid-refresh and
    let a second pod start the same queries.
    """
    query_timeout = int(settings.PLATFORM_METRICS_QUERY_TIMEOUT_MS) / 1000
    return max(_MIN_LOCK_TIMEOUT_SECONDS, group.statements * query_timeout + 10)


class _Lock(Protocol):
    def acquire(self, blocking: bool = ...) -> bool: ...
    def release(self) -> None: ...
    def extend(self, additional_time: float, replace_ttl: bool = ...) -> bool: ...


class RedisLike(Protocol):
    def get(self, name: str) -> Any: ...
    def set(self, name: str, value: str, ex: int | None = ...) -> Any: ...
    def lock(self, name: str, timeout: float | None = ...) -> _Lock: ...
    def pipeline(self, transaction: bool = ...) -> Any: ...


@dataclass(frozen=True)
class CachedSnapshot:
    data: Snapshot
    #: Unix time of the successful refresh that produced ``data``.
    refreshed_at: float

    def age(self, now: float) -> float:
        return now - self.refreshed_at


class RefreshFailed(Exception):
    """A group could not be refreshed. ``snapshot`` is what to serve instead."""

    def __init__(self, snapshot: CachedSnapshot | None) -> None:
        super().__init__("platform metrics refresh failed")
        self.snapshot = snapshot


_client: Any = None
_client_lock = threading.Lock()


def _default_client() -> RedisLike:
    """The backend's Redis, through a pool of its own with bounded waits.

    The shared ``default`` pool sets no socket timeouts, so a Redis that
    accepts connections but stops replying would hold a scrape (and its
    worker thread) indefinitely and the local fallback would never run. The
    metrics pool copies the shared one's settings, Sentinel included, and adds
    ``PLATFORM_METRICS_REDIS_TIMEOUT_SECONDS`` for connecting and reading, so
    a stall surfaces as an error and takes the fallback path. Built once per
    process, on first scrape.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from django_redis import get_redis_connection

                _client = with_timeouts(
                    get_redis_connection("default"),
                    float(settings.PLATFORM_METRICS_REDIS_TIMEOUT_SECONDS),
                )
    return _client


def with_timeouts(client: Any, timeout: float) -> Any:
    """A client on a new pool like ``client``'s, with socket timeouts set."""
    import redis
    from redis.sentinel import SentinelConnectionPool

    pool = client.connection_pool
    # A Sentinel pool stores a back-reference to itself here; the new pool
    # sets its own.
    kwargs = {k: v for k, v in pool.connection_kwargs.items() if k != "connection_pool"}
    kwargs.update(socket_timeout=timeout, socket_connect_timeout=timeout)
    if isinstance(pool, SentinelConnectionPool):
        bounded = SentinelConnectionPool(
            pool.service_name,
            pool.sentinel_manager,
            connection_class=pool.connection_class,
            is_master=pool.is_master,
            check_connection=pool.check_connection,
            **kwargs,
        )
    else:
        bounded = type(pool)(
            connection_class=pool.connection_class,
            max_connections=pool.max_connections,
            **kwargs,
        )
    return redis.Redis(connection_pool=bounded)


#: How long Redis is skipped after a call to it fails, so one stall costs a
#: scrape at most one timeout rather than one per group.
_BREAKER_SECONDS = 5.0


class RedisBreaker:
    """Remembers a recent Redis failure so the next calls skip Redis.

    Without it a stalled Redis costs every group, and the failure counter,
    their own socket timeout in turn on every scrape. Shared by the cache and
    the counter of one exporter.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._open_until = 0.0

    def trip(self) -> None:
        self._open_until = self._clock() + _BREAKER_SECONDS

    def is_open(self) -> bool:
        return self._clock() < self._open_until


class SnapshotCache:
    """Resolves a group to its current snapshot, refreshing when stale."""

    def __init__(
        self,
        client_factory: Callable[[], RedisLike] = _default_client,
        clock: Callable[[], float] = time.time,
        breaker: RedisBreaker | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._clock = clock
        self._breaker = breaker or RedisBreaker(clock)
        # Per-process last-known-good copies: the fallback when Redis is down.
        self._local: dict[str, CachedSnapshot] = {}
        # One lock per group, so a slow refresh of one group never holds up
        # scrapes waiting on another.
        self._local_locks: dict[str, threading.Lock] = {}
        self._local_locks_guard = threading.Lock()
        # When each group last tried a Redis-less refresh, so a failing DB is
        # retried at most once per TTL per process.
        self._local_attempts: dict[str, float] = {}

    @staticmethod
    def _ttl() -> float:
        return float(settings.PLATFORM_METRICS_CACHE_TTL_SECONDS)

    def resolve(self, group: MetricGroup) -> CachedSnapshot | None:
        """Return the snapshot to serve for ``group``.

        Raises :class:`RefreshFailed` (carrying the snapshot to serve anyway)
        when this call tried and failed to refresh the group.
        """
        if self._breaker.is_open():
            return self._resolve_local(group)
        try:
            client = self._client_factory()
            cached = self._newest(group, self._read(client, group))
        except Exception:
            self._breaker.trip()
            logger.warning(
                "platform metrics: Redis unavailable for group %r; using the "
                "process-local snapshot",
                group.name,
                exc_info=True,
            )
            return self._resolve_local(group)

        if cached is not None and cached.age(self._clock()) < self._ttl():
            return cached

        try:
            lock = client.lock(
                self._lock_key(group), timeout=_lock_timeout_seconds(group)
            )
            acquired = lock.acquire(blocking=False)
        except Exception:
            self._breaker.trip()
            logger.warning(
                "platform metrics: could not take the refresh lock for %r",
                group.name,
                exc_info=True,
            )
            return self._resolve_local(group, fallback=cached)
        if not acquired:
            # Another pod is refreshing; its result lands for the next scrape.
            return cached

        held_for_backoff = False
        try:
            # Re-read under the lock: another pod may have refreshed between
            # our read and our acquire.
            try:
                latest = self._newest(group, self._read(client, group))
            except Exception:
                self._breaker.trip()
                logger.warning(
                    "platform metrics: Redis failed re-reading group %r under the lock",
                    group.name,
                    exc_info=True,
                )
                return self._resolve_local(group, fallback=cached)
            if latest is not None and latest.age(self._clock()) < self._ttl():
                return latest
            try:
                snapshot = self._refresh(group, fallback=latest)
            except RefreshFailed:
                held_for_backoff = self._hold_for_backoff(lock, group)
                raise
            try:
                client.set(
                    self._data_key(group),
                    json.dumps(
                        {"data": snapshot.data, "refreshed_at": snapshot.refreshed_at}
                    ),
                    ex=_RETENTION_SECONDS,
                )
            except Exception as e:
                self._breaker.trip()
                # Still good to serve, and kept as this process's copy, which
                # _newest() prefers over the older Redis value until it goes
                # stale, so a write-failing Redis does not turn every scrape
                # into a DB refresh. Counted, since the other pods miss it.
                logger.warning(
                    "platform metrics: could not cache group %r in Redis",
                    group.name,
                    exc_info=True,
                )
                raise RefreshFailed(snapshot) from e
            return snapshot
        finally:
            try:
                if not held_for_backoff:
                    lock.release()
            except Exception:
                # Expired under us (a refresh slower than the lock timeout):
                # nothing to release.
                logger.debug("platform metrics: lock for %r already gone", group.name)

    def _hold_for_backoff(self, lock: _Lock, group: MetricGroup) -> bool:
        """Keep the lock for one TTL after a failed refresh.

        Every pod then serves the last snapshot until it expires, instead of
        the next scrape (KEDA polls several times a second) retrying the same
        queries against a struggling DB. Retries stay at about one per TTL
        cluster-wide. Returns whether the lock is now held.
        """
        try:
            return bool(lock.extend(max(1, int(self._ttl())), replace_ttl=True))
        except Exception:
            logger.debug("platform metrics: could not hold lock for %r", group.name)
            return False

    def _resolve_local(
        self, group: MetricGroup, fallback: CachedSnapshot | None = None
    ) -> CachedSnapshot | None:
        """Redis-less path: refresh this process's copy at most once per TTL.

        Always raises :class:`RefreshFailed`: every scrape that finds Redis
        unusable counts as a failure for the group, even when the snapshot it
        serves is fresh, so a Redis outage shows on the failure counter.
        """
        with self._local_lock(group):
            local = self._local.get(group.name)
            now = self._clock()
            if local is not None and local.age(now) < self._ttl():
                raise RefreshFailed(local)
            last_attempt = self._local_attempts.get(group.name)
            if last_attempt is not None and now - last_attempt < self._ttl():
                # Failed within the TTL: back off rather than retry per scrape.
                raise RefreshFailed(local or fallback)
            self._local_attempts[group.name] = now
            raise RefreshFailed(self._refresh(group, fallback=local or fallback))

    def _local_lock(self, group: MetricGroup) -> threading.Lock:
        with self._local_locks_guard:
            return self._local_locks.setdefault(group.name, threading.Lock())

    def _refresh(
        self, group: MetricGroup, fallback: CachedSnapshot | None
    ) -> CachedSnapshot:
        try:
            data = group.fetch()
        except Exception as e:
            logger.exception("platform metrics: refreshing group %r failed", group.name)
            raise RefreshFailed(fallback or self._local.get(group.name)) from e
        snapshot = CachedSnapshot(data=data, refreshed_at=self._clock())
        self._local[group.name] = snapshot
        return snapshot

    def _read(self, client: RedisLike, group: MetricGroup) -> CachedSnapshot | None:
        raw = client.get(self._data_key(group))  # a Redis error propagates
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            return CachedSnapshot(
                data=payload["data"], refreshed_at=float(payload["refreshed_at"])
            )
        except (ValueError, TypeError, KeyError):
            # Not a Redis outage: treat as missing so a refresh overwrites it,
            # rather than falling back to per-process refreshes until it expires.
            logger.warning(
                "platform metrics: ignoring unreadable cache entry for group %r",
                group.name,
            )
            return None

    def _newest(
        self, group: MetricGroup, shared: CachedSnapshot | None
    ) -> CachedSnapshot | None:
        """The newer of the Redis snapshot and this process's copy, kept locally.

        The local copy can be the newer one when this pod refreshed but could
        not write the result back to Redis.
        """
        local = self._local.get(group.name)
        if shared is None or (
            local is not None and local.refreshed_at >= shared.refreshed_at
        ):
            return local
        self._local[group.name] = shared
        return shared

    @staticmethod
    def _data_key(group: MetricGroup) -> str:
        return f"{_KEY_PREFIX}:data:{group.name}"

    @staticmethod
    def _lock_key(group: MetricGroup) -> str:
        return f"{_KEY_PREFIX}:lock:{group.name}"


class FailureCounter:
    """Refresh-failure totals per group, shared through Redis.

    Increments are buffered in-process and flushed with ``HINCRBY`` together
    with the read, in one transactional pipeline. A failure recorded while
    Redis is down is added on this process's next successful scrape; it is
    lost if the process exits first, so the total is best-effort during a
    Redis outage. While Redis is unreachable, :meth:`totals` returns ``None``
    and the counter is left out of the scrape rather than dropping to this
    process's partial count, which Prometheus would read as a reset; the
    exporter's ``unstract_metrics_cache_up`` gauge reports the outage instead.
    """

    def __init__(
        self,
        client_factory: Callable[[], RedisLike] = _default_client,
        breaker: RedisBreaker | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._breaker = breaker or RedisBreaker()
        self._pending: dict[str, int] = {}
        self._lock = threading.Lock()

    def record(self, group: str) -> None:
        with self._lock:
            self._pending[group] = self._pending.get(group, 0) + 1

    def totals(self) -> dict[str, int] | None:
        """Flush pending increments, then read the shared totals."""
        # Take the pending counts and do the Redis I/O outside the lock, so a
        # slow Redis never blocks record() on another thread.
        if self._breaker.is_open():
            return None
        with self._lock:
            pending, self._pending = self._pending, {}
        try:
            pipe = self._client_factory().pipeline(transaction=True)
            for group, amount in pending.items():
                pipe.hincrby(_FAILURES_KEY, group, amount)
            pipe.hgetall(_FAILURES_KEY)
            raw = pipe.execute()[-1]
        except Exception:
            self._breaker.trip()
            self._restore(pending)
            logger.warning(
                "platform metrics: could not read refresh-failure totals", exc_info=True
            )
            return None
        totals: dict[str, int] = {}
        for key, value in raw.items():
            try:
                totals[_text(key)] = int(value)
            except (ValueError, TypeError):
                logger.warning(
                    "platform metrics: ignoring unreadable failure total %r", key
                )
        return totals

    def _restore(self, pending: dict[str, int]) -> None:
        with self._lock:
            for group, amount in pending.items():
                self._pending[group] = self._pending.get(group, 0) + amount


#: No expiry: the totals must only grow. A Redis flush resets them to 0, which
#: Prometheus handles as an ordinary counter reset.
_FAILURES_KEY = f"{_KEY_PREFIX}:refresh_failures"


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
