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

    def extend(self, additional_time: float, replace_ttl: bool = False) -> bool:
        if not self.owned:
            raise RuntimeError("not owned")
        self._redis.lock_ttls[self._name] = additional_time
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
        #: TTL set by Lock.extend(); expiry itself is simulated by the test.
        self.lock_ttls: dict[str, float] = {}
        self.hashes: dict[str, dict[str, int]] = {}
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
        self.last_lock_timeout = timeout
        return FakeLock(self, name)

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)

    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        self._check()
        bucket = self.hashes.setdefault(name, {})
        bucket[key] = bucket.get(key, 0) + amount
        return bucket[key]

    def hgetall(self, name: str) -> dict[bytes, bytes]:
        self._check()
        return {
            k.encode(): str(v).encode() for k, v in self.hashes.get(name, {}).items()
        }


class FakePipeline:
    """Queues calls and applies them on execute(), all or nothing."""

    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._calls: list[tuple[str, tuple]] = []

    def hincrby(self, *args) -> None:
        self._calls.append(("hincrby", args))

    def hgetall(self, *args) -> None:
        self._calls.append(("hgetall", args))

    def execute(self) -> list:
        self._redis._check()
        return [getattr(self._redis, name)(*args) for name, args in self._calls]


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
