"""Assembles the platform metric groups into one Prometheus exposition.

A collector resolves every group through
the shared :class:`~platform_metrics.cache.SnapshotCache` at scrape time and
reports refresh failures from the Redis-shared
:class:`~platform_metrics.cache.FailureCounter`. Each group is resolved inside
its own ``try``, so one failing group never blanks the others and the scrape
itself always succeeds.

Each render builds its own registry rather than using ``prometheus_client``'s
default ``REGISTRY``, so nothing else in the process can leak series into this
endpoint, and a scrape can select a subset of groups.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING

from .cache import FailureCounter, RedisBreaker, RefreshFailed, SnapshotCache
from .groups import METRIC_GROUPS, MetricGroup

if TYPE_CHECKING:
    from prometheus_client.core import Metric

logger = logging.getLogger(__name__)


class _GroupsCollector:
    def __init__(
        self,
        groups: Sequence[MetricGroup],
        cache: SnapshotCache,
        failures: FailureCounter,
        clock: Callable[[], float],
    ) -> None:
        self._groups = groups
        self._cache = cache
        self._failures = failures
        self._clock = clock

    def describe(self) -> Iterable[Metric]:
        # Present so register() does not run collect() (and the DB) on import.
        return []

    def collect(self) -> Iterable[Metric]:
        from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

        refreshed = GaugeMetricFamily(
            "unstract_metrics_last_successful_refresh_timestamp",
            "Unix time of the last successful refresh of each metric group "
            "(alert on time() minus this)",
            labels=["group"],
        )
        families: list[Metric] = []
        for group in self._groups:
            try:
                snapshot = self._cache.resolve(group)
            except RefreshFailed as failed:
                self._failures.record(group.name)
                snapshot = failed.snapshot
            except Exception:
                logger.exception("platform metrics: group %r failed", group.name)
                self._failures.record(group.name)
                snapshot = None
            if snapshot is None:
                continue
            # The refresh timestamp is still reported, so the age stays visible.
            refreshed.add_metric([group.name], snapshot.refreshed_at)
            limit = group.max_staleness_seconds
            if limit is not None and snapshot.age(self._clock()) > limit:
                logger.warning(
                    "platform metrics: group %r is %.0fs old; leaving it out",
                    group.name,
                    snapshot.age(self._clock()),
                )
                continue
            try:
                families.extend(group.families(snapshot.data))
            except Exception:
                # A cached snapshot that no longer fits the group (e.g. written
                # by an older pod mid-deploy) is dropped, not served half-built.
                logger.exception(
                    "platform metrics: rendering group %r failed", group.name
                )
                self._failures.record(group.name)
                continue
        families.append(refreshed)
        # Read after the groups, so failures from this scrape are included.
        totals = self._failures.totals()
        families.append(
            GaugeMetricFamily(
                "unstract_metrics_cache_up",
                "1 when this process could reach the Redis metrics cache on this "
                "scrape, else 0 (groups then serve per-process copies and the "
                "failure counter is left out)",
                value=0 if totals is None else 1,
            )
        )
        if totals is not None:
            failures = CounterMetricFamily(
                "unstract_metrics_refresh_failures",
                "Failed refreshes per metric group. One cluster-wide total kept "
                "in Redis, so every backend pod reports the same value: "
                "aggregate across instances with max(), not sum(). The group "
                "serves its last cached values meanwhile",
                labels=["group"],
            )
            for group in self._groups:
                # Every group's series exists, so one that never failed reads 0.
                failures.add_metric([group.name], totals.get(group.name, 0))
            families.append(failures)
        return families


class UnknownGroup(ValueError):
    """A requested group name matches no registered metric group."""


class PlatformMetricsExporter:
    def __init__(
        self,
        groups: Sequence[MetricGroup] = METRIC_GROUPS,
        cache: SnapshotCache | None = None,
        failures: FailureCounter | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._groups = tuple(groups)
        # One breaker for both, so a Redis failure seen by the cache also
        # spares the counter its timeout, and the other way round.
        breaker = RedisBreaker()
        self._cache = cache or SnapshotCache(breaker=breaker)
        self._failures = failures or FailureCounter(breaker=breaker)
        self._clock = clock

    def render(self, group_names: Sequence[str] | None = None) -> bytes:
        """The exposition for every group, or only ``group_names``.

        Selecting groups lets a reader that needs one group (an autoscaler
        polling queue depth, with a short HTTP timeout) skip the others'
        refreshes. Raises :class:`UnknownGroup` for a name that matches none.
        """
        from prometheus_client import CollectorRegistry, generate_latest

        groups = self._groups
        if group_names:
            known = {group.name for group in groups}
            unknown = sorted(set(group_names) - known)
            if unknown:
                raise UnknownGroup(", ".join(unknown))
            groups = tuple(group for group in groups if group.name in group_names)
        # A registry per render, so it holds exactly the selected groups. It
        # is instance-owned, so nothing else in the process leaks series in.
        registry = CollectorRegistry()
        registry.register(
            _GroupsCollector(groups, self._cache, self._failures, self._clock)
        )
        return generate_latest(registry)


_exporter: PlatformMetricsExporter | None = None
_exporter_lock = threading.Lock()


def get_exporter() -> PlatformMetricsExporter:
    """The process-wide exporter, built on first scrape."""
    global _exporter
    if _exporter is None:
        with _exporter_lock:
            if _exporter is None:
                _exporter = PlatformMetricsExporter()
    return _exporter
