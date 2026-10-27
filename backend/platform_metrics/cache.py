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
  process's copy) and count the failure;
* Redis is unreachable: fall back to this process's copy, refreshing it from
  the DB at most once per TTL, so DB load stays bounded per pod rather than
  per scrape. The failure is counted;
* nothing has ever been fetched (first scrape, while another pod holds the
  lock): the group is left out of this scrape.
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
#: Lock expiry. Above the statement timeout, so a pod that dies mid-refresh
#: frees the group within one window instead of wedging it.
_LOCK_TIMEOUT_SECONDS = 30


class _Lock(Protocol):
    def acquire(self, blocking: bool = ...) -> bool: ...
    def release(self) -> None: ...


class RedisLike(Protocol):
    def get(self, name: str) -> Any: ...
    def set(self, name: str, value: str, ex: int | None = ...) -> Any: ...
    def lock(self, name: str, timeout: float | None = ...) -> _Lock: ...


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


def _default_client() -> RedisLike:
    from django_redis import get_redis_connection

    return get_redis_connection("default")


class SnapshotCache:
    """Resolves a group to its current snapshot, refreshing when stale."""

    def __init__(
        self,
        client_factory: Callable[[], RedisLike] = _default_client,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client_factory = client_factory
        self._clock = clock
        # Per-process last-known-good copies: the fallback when Redis is down.
        self._local: dict[str, CachedSnapshot] = {}
        self._local_lock = threading.Lock()

    @staticmethod
    def _ttl() -> float:
        return float(settings.PLATFORM_METRICS_CACHE_TTL_SECONDS)

    def resolve(self, group: MetricGroup) -> CachedSnapshot | None:
        """Return the snapshot to serve for ``group``.

        Raises :class:`RefreshFailed` (carrying the snapshot to serve anyway)
        when this call tried and failed to refresh the group.
        """
        try:
            client = self._client_factory()
            cached = self._read(client, group)
        except Exception:
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
            lock = client.lock(self._lock_key(group), timeout=_LOCK_TIMEOUT_SECONDS)
            acquired = lock.acquire(blocking=False)
        except Exception:
            logger.warning(
                "platform metrics: could not take the refresh lock for %r",
                group.name,
                exc_info=True,
            )
            return self._resolve_local(group, fallback=cached)
        if not acquired:
            # Another pod is refreshing; its result lands for the next scrape.
            return cached or self._local.get(group.name)

        try:
            # Re-read under the lock: another pod may have refreshed between
            # our read and our acquire.
            latest = self._read(client, group)
            if latest is not None and latest.age(self._clock()) < self._ttl():
                return latest
            snapshot = self._refresh(group, fallback=latest or cached)
            try:
                client.set(
                    self._data_key(group),
                    json.dumps(
                        {"data": snapshot.data, "refreshed_at": snapshot.refreshed_at}
                    ),
                    ex=_RETENTION_SECONDS,
                )
            except Exception:
                # The fresh snapshot is still good to serve from this pod.
                logger.warning(
                    "platform metrics: could not cache group %r in Redis",
                    group.name,
                    exc_info=True,
                )
            return snapshot
        finally:
            try:
                lock.release()
            except Exception:
                # Expired under us (a refresh slower than the lock timeout):
                # nothing to release.
                logger.debug("platform metrics: lock for %r already gone", group.name)

    def _resolve_local(
        self, group: MetricGroup, fallback: CachedSnapshot | None = None
    ) -> CachedSnapshot | None:
        """Redis-less path: refresh this process's copy at most once per TTL.

        Always raises :class:`RefreshFailed`: every scrape that finds Redis
        unusable counts as a failure for the group, even when the snapshot it
        serves is fresh, so a Redis outage shows on the failure counter.
        """
        with self._local_lock:
            local = self._local.get(group.name)
            if local is not None and local.age(self._clock()) < self._ttl():
                raise RefreshFailed(local)
            raise RefreshFailed(self._refresh(group, fallback=local or fallback))

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
        raw = client.get(self._data_key(group))
        if raw is None:
            return None
        payload = json.loads(raw)
        snapshot = CachedSnapshot(
            data=payload["data"], refreshed_at=float(payload["refreshed_at"])
        )
        self._local[group.name] = snapshot
        return snapshot

    @staticmethod
    def _data_key(group: MetricGroup) -> str:
        return f"{_KEY_PREFIX}:data:{group.name}"

    @staticmethod
    def _lock_key(group: MetricGroup) -> str:
        return f"{_KEY_PREFIX}:lock:{group.name}"
