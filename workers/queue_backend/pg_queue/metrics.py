"""Prometheus metrics for PG-queue processes (application-level exporter).

Today's queue observability comes from RabbitMQ's built-in Prometheus plugin;
Postgres has no such plugin — the pg_queue tables ARE the broker — so the
exporter is ours. This module holds the metric *definitions*; the SQL that
feeds the queue-wide gauges lives with its sibling queries in ``reaper.py``
(it shares the stranded-barrier predicate), and the HTTP surface is the
existing :class:`~queue_backend.pg_queue.liveness.LivenessServer` ``/metrics``
route — no new port, no new server, no execution-path changes.

Two exporters, matching the two process shapes:

- :class:`ConsumerMetrics` — per-pod, on every PG worker: poll-loop heartbeat
  freshness (the same signal ``/health`` verdicts on, as a scrapeable number).
- :class:`ReaperMetrics` — queue-WIDE state, exported only by the reaper: it is
  the leader-elected singleton, so queue depth / oldest-message age / barrier
  counts come from one process instead of N pods running identical SQL and
  emitting duplicate series. Standbys export zeroed queue gauges and
  ``is_leader 0``.

Registries are instance-owned (never the ``prometheus_client`` default
``REGISTRY``): the workers tree is imported under more than one module name in
places (the bare-``tasks`` sys.path quirk), and module-level collectors would
double-register on the second import. An instance per process cannot.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

logger = logging.getLogger(__name__)

# Prometheus text exposition format (the /metrics Content-Type).
METRICS_CONTENT_TYPE: Final = "text/plain; version=0.0.4; charset=utf-8"


def _new_registry() -> CollectorRegistry:
    from prometheus_client import CollectorRegistry

    return CollectorRegistry()


def _render(registry: CollectorRegistry) -> bytes:
    from prometheus_client import generate_latest

    return generate_latest(registry)


class ConsumerMetrics:
    """Per-pod metrics for a PG-queue consumer (or the fleet supervisor).

    ``freshness_fn`` is the same heartbeat the liveness probe reads —
    seconds since the poll loop last made progress (for the supervisor, the
    OLDEST child's, so one wedged child surfaces). The optional fleet hooks
    exist because the supervisor's ``/health`` JSON already reports them and
    an operator graphing the fleet needs them as numbers, not JSON.
    """

    def __init__(
        self,
        *,
        freshness_fn: Callable[[], float],
        alive_children_fn: Callable[[], float] | None = None,
        concurrency_fn: Callable[[], float] | None = None,
    ) -> None:
        from prometheus_client import Gauge

        self.registry = _new_registry()
        heartbeat = Gauge(
            "pg_consumer_heartbeat_age_seconds",
            "Seconds since the consumer poll loop last made progress "
            "(the liveness heartbeat; /health goes 503 past its stale window)",
            registry=self.registry,
        )
        heartbeat.set_function(freshness_fn)
        if alive_children_fn is not None:
            alive = Gauge(
                "pg_consumer_alive_children",
                "Live child consumer processes in the supervisor fleet",
                registry=self.registry,
            )
            alive.set_function(alive_children_fn)
        if concurrency_fn is not None:
            conc = Gauge(
                "pg_consumer_configured_concurrency",
                "Configured child-process concurrency of the supervisor fleet",
                registry=self.registry,
            )
            conc.set_function(concurrency_fn)

    def render(self) -> bytes:
        return _render(self.registry)


class ReaperMetrics:
    """Queue-wide + reaper-outcome metrics, exported by the reaper process.

    The queue gauges (`pg_queue_depth`, oldest-message age, barrier counts) are
    CACHED snapshots — the reaper refreshes them on its own cadence (leader
    only) and a scrape never touches the DB, so a hot scraper (or a curl loop
    during an incident) cannot add DB load. ``pg_queue_gauges_age_seconds``
    exposes the snapshot's staleness so a reader can tell cached-fresh from
    cached-dead; it reads 0 while no snapshot has ever been taken (standby) —
    disambiguate with ``pg_reaper_is_leader``.

    Outcome counters are incremented by the recovery/sweep code at the same
    sites that log the outcomes (see ``reaper.py``).
    """

    def __init__(
        self,
        *,
        heartbeat_fn: Callable[[], float],
        is_leader_fn: Callable[[], bool],
    ) -> None:
        from prometheus_client import Counter, Gauge

        self.registry = _new_registry()

        heartbeat = Gauge(
            "pg_reaper_heartbeat_age_seconds",
            "Seconds since the reaper tick loop last ran (liveness heartbeat)",
            registry=self.registry,
        )
        heartbeat.set_function(heartbeat_fn)
        leader = Gauge(
            "pg_reaper_is_leader",
            "1 while this reaper holds the leader lease, else 0",
            registry=self.registry,
        )
        leader.set_function(lambda: 1.0 if is_leader_fn() else 0.0)

        self.barrier_recovered = Counter(
            "pg_reaper_barrier_recovered_total",
            "Stranded barriers recovered (execution marked ERROR + rows removed)",
            registry=self.registry,
        )
        self.barrier_recovery_failures = Counter(
            "pg_reaper_barrier_recovery_failures_total",
            "Stranded-barrier recovery attempts that raised (row left for retry)",
            registry=self.registry,
        )
        self.claim_recovered = Counter(
            "pg_reaper_claim_recovered_total",
            "Orphan orchestration claims recovered (crash-window execution "
            "marked ERROR)",
            registry=self.registry,
        )
        self.claim_gc = Counter(
            "pg_reaper_claim_gc_total",
            "Orphan orchestration-claim tombstones GC'd (execution already " "terminal)",
            registry=self.registry,
        )
        self.claim_recovery_failures = Counter(
            "pg_reaper_claim_recovery_failures_total",
            "Orphan-claim recovery attempts that raised (row left for retry)",
            registry=self.registry,
        )
        self.sweep_failures = Counter(
            "pg_reaper_sweep_failures_total",
            "Whole-sweep failures, by swept table (see the reaper fail-streak log)",
            ["table"],
            registry=self.registry,
        )
        self.gauge_refresh_failures = Counter(
            "pg_reaper_gauge_refresh_failures_total",
            "Failed queue-gauge snapshot refreshes (metrics stale, queue unaffected)",
            registry=self.registry,
        )

        self._queue_depth = Gauge(
            "pg_queue_depth",
            "Messages currently in pg_queue_message, by queue (cached snapshot)",
            ["queue"],
            registry=self.registry,
        )
        self._oldest_age = Gauge(
            "pg_queue_oldest_message_age_seconds",
            "Age of the oldest message in the queue (cached snapshot)",
            ["queue"],
            registry=self.registry,
        )
        self._barriers_live = Gauge(
            "pg_barrier_live",
            "pg_barrier_state rows with remaining > 0 (in-flight fan-outs)",
            registry=self.registry,
        )
        self._barriers_stranded = Gauge(
            "pg_barrier_stranded",
            "Live barriers past the stuck-timeout / expiry (reaper will recover)",
            registry=self.registry,
        )
        self._last_refresh_monotonic: float | None = None
        gauges_age = Gauge(
            "pg_queue_gauges_age_seconds",
            "Seconds since the queue gauges were last refreshed (0 = never; "
            "check pg_reaper_is_leader)",
            registry=self.registry,
        )
        gauges_age.set_function(self._seconds_since_refresh)

    def _seconds_since_refresh(self) -> float:
        if self._last_refresh_monotonic is None:
            return 0.0
        return time.monotonic() - self._last_refresh_monotonic

    def set_queue_snapshot(
        self,
        *,
        depths: dict[str, tuple[int, float]],
        barriers_live: int,
        barriers_stranded: int,
    ) -> None:
        """Replace the cached queue-wide snapshot.

        ``depths`` maps queue name -> (message count, oldest-message age in
        seconds). Series are cleared first so a queue that drained to zero
        drops out rather than freezing at its last non-zero value.
        """
        self._queue_depth.clear()
        self._oldest_age.clear()
        for queue, (depth, oldest_age) in depths.items():
            self._queue_depth.labels(queue=queue).set(depth)
            self._oldest_age.labels(queue=queue).set(oldest_age)
        self._barriers_live.set(barriers_live)
        self._barriers_stranded.set(barriers_stranded)
        self._last_refresh_monotonic = time.monotonic()

    def clear_queue_snapshot(self) -> None:
        """Zero the queue-wide gauges (called on losing leadership, so a standby
        never exports a frozen stale snapshot as if it were live).
        """
        self._queue_depth.clear()
        self._oldest_age.clear()
        self._barriers_live.set(0)
        self._barriers_stranded.set(0)
        self._last_refresh_monotonic = None

    def render(self) -> bytes:
        return _render(self.registry)
