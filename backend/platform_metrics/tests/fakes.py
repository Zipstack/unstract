"""In-memory stand-ins for Redis and metric groups (DB- and Redis-free tests)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from platform_metrics.groups import MetricGroup, Snapshot


class FakeLock:
    def __init__(self, redis: FakeRedis, name: str) -> None:
        self._redis = redis
        self._name = name
        self.owned = False

    def acquire(self, blocking: bool = True) -> bool:
        if self._name in self._redis.locks:
            return False
        self._redis.locks.add(self._name)
        self.owned = True
        return True

    def release(self) -> None:
        if not self.owned:
            raise RuntimeError("not owned")
        self._redis.locks.discard(self._name)
        self.owned = False


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.expiry: dict[str, int | None] = {}
        self.locks: set[str] = set()
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise ConnectionError("redis down")

    def get(self, name: str) -> Any:
        self._check()
        value = self.data.get(name)
        return value.encode() if value is not None else None

    def set(self, name: str, value: str, ex: int | None = None) -> bool:
        self._check()
        self.data[name] = value
        self.expiry[name] = ex
        return True

    def lock(self, name: str, timeout: float | None = None) -> FakeLock:
        self._check()
        return FakeLock(self, name)


class StubGroup(MetricGroup):
    """A group whose fetch result (or failure) the test controls."""

    def __init__(self, name: str, value: float = 1.0) -> None:
        self.name = name
        self.value = value
        self.fetches = 0
        self.error: Exception | None = None

    def fetch(self) -> Snapshot:
        self.fetches += 1
        if self.error is not None:
            raise self.error
        return {"value": self.value}

    def query(self) -> Snapshot:  # pragma: no cover - fetch is overridden
        raise NotImplementedError

    def families(self, snapshot: Snapshot) -> Iterable[Any]:
        from prometheus_client.core import GaugeMetricFamily

        return [
            GaugeMetricFamily(
                f"stub_{self.name}", "stub metric", value=snapshot["value"]
            )
        ]


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now
