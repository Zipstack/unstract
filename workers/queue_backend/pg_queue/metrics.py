"""Prometheus metrics for PG-queue processes (application-level exporter).

Today's queue observability comes from RabbitMQ's built-in Prometheus plugin;
Postgres has no such plugin — the pg_queue tables ARE the broker — so the
exporter is ours. This module holds the metric *definitions*; the SQL that
feeds the queue-wide gauges lives with its sibling queries in ``reaper.py``
(it shares the stranded-barrier predicate), and the HTTP surface is the
existing :class:`~queue_backend.pg_queue.liveness.LivenessServer` ``/metrics``
route — no new port, no new server, no execution-path changes.

Two exporters, matching the two process shapes:

- :class:`ConsumerMetrics` — per-pod, on every PG consumer: poll-loop heartbeat
  freshness (the same signal ``/health`` verdicts on, as a scrapeable number).
- :class:`ReaperMetrics` — queue-WIDE state, exported only by the reaper: it is
  the leader-elected singleton, so queue depth / oldest-message age / barrier
  counts come from one process instead of N pods running identical SQL and
  emitting duplicate series. On a standby the per-queue series are absent and
  the barrier gauges read 0 — disambiguate with ``pg_reaper_is_leader``.

The queue-wide gauges are backed by ONE immutable snapshot object swapped by
reference (:class:`_QueueSnapshot`): a scrape reads a single consistent
snapshot, so it can never observe a torn state (new depths with old barrier
counts) or race the tick thread's clear — the swap is atomic and the render
side never reads mutable fields twice.

Registries are instance-owned (never the ``prometheus_client`` default
``REGISTRY``): the workers tree is imported under more than one module name in
places (the bare-``tasks`` sys.path quirk), and module-level collectors would
double-register on the second import. An instance per process cannot.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry
    from prometheus_client.core import Metric

logger = logging.getLogger(__name__)

# Prometheus text exposition format (the /metrics Content-Type).
METRICS_CONTENT_TYPE: Final = "text/plain; version=0.0.4; charset=utf-8"


def _new_registry() -> CollectorRegistry:
    from prometheus_client import CollectorRegistry

    return CollectorRegistry()


class _Exporter:
    """Shared exporter shell: an instance-owned registry + text render."""

    def __init__(self) -> None:
        self.registry = _new_registry()

    def _function_gauge(self, name: str, doc: str, fn: Callable[[], float]) -> None:
        from prometheus_client import Gauge

        Gauge(name, doc, registry=self.registry).set_function(fn)

    def render(self) -> bytes:
        from prometheus_client import generate_latest

        return generate_latest(self.registry)


class ConsumerMetrics(_Exporter):
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
        super().__init__()
        self._function_gauge(
            "pg_consumer_heartbeat_age_seconds",
            "Seconds since the consumer poll loop last made progress "
            "(the liveness heartbeat; /health goes 503 past its stale window)",
            freshness_fn,
        )
        if alive_children_fn is not None:
            self._function_gauge(
                "pg_consumer_alive_children",
                "Live child consumer processes in the supervisor fleet",
                alive_children_fn,
            )
        if concurrency_fn is not None:
            self._function_gauge(
                "pg_consumer_configured_concurrency",
                "Configured child-process concurrency of the supervisor fleet",
                concurrency_fn,
            )


@dataclass(frozen=True)
class _QueueSnapshot:
    """One immutable queue-wide observation, swapped into the collector by
    reference — the atomicity unit for scrapes.

    ``reference_monotonic`` anchors ``pg_queue_gauges_age_seconds``: the refresh
    time for a real snapshot, or the construction/step-down time for an empty
    one — so a leader whose refresh has been failing since boot shows an
    ever-GROWING age (a staleness alert can fire) instead of a frozen 0.
    """

    depths: Mapping[str, tuple[int, float]] = field(default_factory=dict)
    barriers_live: int = 0
    barriers_stranded: int = 0
    reference_monotonic: float = field(default_factory=time.monotonic)


class _QueueSnapshotCollector:
    """Custom collector rendering the current :class:`_QueueSnapshot`.

    ``collect`` reads ``self._snapshot`` exactly once, so a concurrent
    ``replace`` (tick thread) can never tear a scrape (HTTP thread) — the
    scrape sees the whole old snapshot or the whole new one.
    """

    def __init__(self) -> None:
        self._snapshot = _QueueSnapshot()

    def replace(self, snapshot: _QueueSnapshot) -> None:
        self._snapshot = snapshot  # atomic reference swap

    @staticmethod
    def _families() -> tuple[Metric, ...]:
        """The five empty metric families — one builder so ``describe`` (names
        only) and ``collect`` (names + samples) can never drift.
        """
        from prometheus_client.core import GaugeMetricFamily

        return (
            GaugeMetricFamily(
                "pg_queue_depth",
                "Messages currently in pg_queue_message, by queue (cached "
                "snapshot; a drained queue's series is absent, not 0)",
                labels=["queue"],
            ),
            GaugeMetricFamily(
                "pg_queue_oldest_message_age_seconds",
                "Age of the oldest message in the queue (cached snapshot)",
                labels=["queue"],
            ),
            GaugeMetricFamily(
                "pg_barrier_live",
                "pg_barrier_state rows with remaining > 0 (in-flight fan-outs)",
            ),
            GaugeMetricFamily(
                "pg_barrier_stranded",
                "Barrier rows past the stuck-timeout / expiry — what the next "
                "recovery pass picks up (includes remaining==0 lingerers)",
            ),
            GaugeMetricFamily(
                "pg_queue_gauges_age_seconds",
                "Seconds since the queue gauges were last refreshed (since "
                "process start / leadership step-down if never) — alert on "
                "this AND pg_reaper_is_leader==1; a standby's age grows by "
                "design",
            ),
        )

    def describe(self) -> Iterable[Metric]:
        # Registration protocol: with describe() present, register() checks
        # names against these descriptors instead of invoking the full
        # collect() render path (and its clock read) as a side effect.
        return self._families()

    def collect(self) -> Iterable[Metric]:
        snapshot = self._snapshot  # single read — the consistency point
        depth, oldest, live, stranded, age = self._families()
        for queue, (msg_count, oldest_age) in snapshot.depths.items():
            depth.add_metric([queue], msg_count)
            oldest.add_metric([queue], oldest_age)
        live.add_metric([], snapshot.barriers_live)
        stranded.add_metric([], snapshot.barriers_stranded)
        age.add_metric([], time.monotonic() - snapshot.reference_monotonic)
        return (depth, oldest, live, stranded, age)


class ReaperMetrics(_Exporter):
    """Queue-wide + reaper-outcome metrics, exported by the reaper process.

    The queue gauges are CACHED snapshots — the reaper refreshes them on its
    own cadence (leader only) and a scrape never touches the DB, so a hot
    scraper (or a curl loop during an incident) cannot add DB load.
    ``pg_queue_gauges_age_seconds`` exposes snapshot staleness and keeps
    growing while refreshes fail or the process is a standby.

    Outcome counters are incremented by the recovery/sweep code at the same
    sites that log the outcomes (see ``reaper.py``).
    """

    def __init__(
        self,
        *,
        heartbeat_fn: Callable[[], float],
        is_leader_fn: Callable[[], bool],
    ) -> None:
        from prometheus_client import Counter

        super().__init__()
        self._function_gauge(
            "pg_reaper_heartbeat_age_seconds",
            "Seconds since the reaper tick loop last ran (liveness heartbeat)",
            heartbeat_fn,
        )
        self._function_gauge(
            "pg_reaper_is_leader",
            "1 while this reaper holds the leader lease, else 0",
            lambda: 1.0 if is_leader_fn() else 0.0,
        )

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
        self.queue_rearmed = Counter(
            "pg_reaper_queue_rearmed_total",
            "Expired in-flight queue messages re-armed to 'ready' (UN-3445: "
            "crashed-worker redelivery — the state-machine equivalent of the old "
            "implicit vt-expiry self-heal)",
            registry=self.registry,
        )
        self.queue_rearm_failures = Counter(
            "pg_reaper_queue_rearm_failures_total",
            "Re-arm sweep attempts that raised (crashed-worker redelivery stalled "
            "this tick; distinguishes a redelivery outage from barrier/scheduler "
            "faults that share pg_reaper_tick_failures_total)",
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
            "Orphan orchestration-claim tombstones GC'd (execution terminal)",
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
        self.tick_failures = Counter(
            "pg_reaper_tick_failures_total",
            "Reaper cycles that raised (recovery/scheduler SELECT failures — the "
            "heartbeat stays fresh through these, so alert on this counter)",
            registry=self.registry,
        )
        self.gauge_refresh_failures = Counter(
            "pg_reaper_gauge_refresh_failures_total",
            "Failed queue-gauge snapshot refreshes (metrics stale, queue unaffected)",
            registry=self.registry,
        )

        self._queue_collector = _QueueSnapshotCollector()
        self.registry.register(self._queue_collector)

    def set_queue_snapshot(
        self,
        *,
        depths: dict[str, tuple[int, float]],
        barriers_live: int,
        barriers_stranded: int,
    ) -> None:
        """Publish a fresh queue-wide snapshot (atomic swap; see collector).

        ``depths`` maps queue name -> (message count, oldest-message age in
        seconds). A queue that drained to zero rows simply drops out of the
        series rather than freezing at its last non-zero value.
        """
        self._queue_collector.replace(
            _QueueSnapshot(
                depths=dict(depths),
                barriers_live=barriers_live,
                barriers_stranded=barriers_stranded,
            )
        )

    def clear_queue_snapshot(self) -> None:
        """Drop the per-queue series and zero the barrier gauges (called on
        losing leadership — a standby must not export a frozen stale snapshot
        as if it were live; its ``pg_queue_gauges_age_seconds`` restarts from
        the step-down and keeps growing).
        """
        self._queue_collector.replace(_QueueSnapshot())
