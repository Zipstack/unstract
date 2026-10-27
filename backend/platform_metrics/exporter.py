"""Assembles the platform metric groups into one Prometheus exposition.

One process-wide registry holds two things: the refresh-failure counter, which
must survive across scrapes, and a collector that resolves every group through
the shared :class:`~platform_metrics.cache.SnapshotCache` at scrape time. Each
group is resolved inside its own ``try``, so one failing group never blanks the
others and the scrape itself always succeeds.

The registry is instance-owned rather than ``prometheus_client``'s default
``REGISTRY``, so nothing else in the process can leak series into this
endpoint and building it twice (tests) cannot double-register.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from .cache import RefreshFailed, SnapshotCache
from .groups import METRIC_GROUPS, MetricGroup

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry, Counter
    from prometheus_client.core import Metric

logger = logging.getLogger(__name__)


class _GroupsCollector:
    def __init__(
        self,
        groups: Sequence[MetricGroup],
        cache: SnapshotCache,
        failures: Counter,
    ) -> None:
        self._groups = groups
        self._cache = cache
        self._failures = failures

    def describe(self) -> Iterable[Metric]:
        # Present so register() does not run collect() (and the DB) on import.
        return []

    def collect(self) -> Iterable[Metric]:
        from prometheus_client.core import GaugeMetricFamily

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
                self._failures.labels(group=group.name).inc()
                snapshot = failed.snapshot
            except Exception:
                logger.exception("platform metrics: group %r failed", group.name)
                self._failures.labels(group=group.name).inc()
                snapshot = None
            if snapshot is None:
                continue
            try:
                families.extend(group.families(snapshot.data))
            except Exception:
                # A cached snapshot that no longer fits the group (e.g. written
                # by an older pod mid-deploy) is dropped, not served half-built.
                logger.exception(
                    "platform metrics: rendering group %r failed", group.name
                )
                self._failures.labels(group=group.name).inc()
                continue
            refreshed.add_metric([group.name], snapshot.refreshed_at)
        families.append(refreshed)
        return families


class PlatformMetricsExporter:
    def __init__(
        self,
        groups: Sequence[MetricGroup] = METRIC_GROUPS,
        cache: SnapshotCache | None = None,
    ) -> None:
        from prometheus_client import CollectorRegistry, Counter

        self.registry: CollectorRegistry = CollectorRegistry()
        self.failures = Counter(
            "unstract_metrics_refresh_failures",
            "Failed refreshes per metric group; the group serves its last "
            "cached values meanwhile",
            ["group"],
            registry=None,
        )
        for group in groups:
            # Pre-create every series so a group that has never failed reads 0.
            self.failures.labels(group=group.name)
        # Order matters: a registry collects in registration order, and the
        # groups collector is what increments the counter, so it goes first
        # for a failure to show in the same scrape that hit it.
        self.registry.register(
            _GroupsCollector(groups, cache or SnapshotCache(), self.failures)
        )
        self.registry.register(self.failures)

    def render(self) -> bytes:
        from prometheus_client import generate_latest

        return generate_latest(self.registry)


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
