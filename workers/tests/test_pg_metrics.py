"""PG-queue application-level metrics exporter (UN-3672).

Covers the four layers:
- the ``/metrics`` route on the shared LivenessServer (opt-in, isolated from
  ``/health``),
- the metric definitions (``ConsumerMetrics`` / ``ReaperMetrics`` — instance
  registries, atomic snapshot swap semantics),
- the reaper wiring (outcome counters threaded into the recovery/sweep
  functions; the cadence-gated, best-effort queue-gauge refresh in ``tick``;
  cadence reset on leadership step-down),
- the supervisor's fleet-metrics wiring (only producer of the fleet gauges).

Float assertions use ``pytest.approx`` throughout — the values are exact
(set/inc of integers), but approx keeps the comparisons robust and quiet.
"""

from __future__ import annotations

import contextlib
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

import queue_backend.pg_queue.reaper as reaper_mod
from queue_backend.pg_queue.liveness import LivenessServer
from queue_backend.pg_queue.metrics import (
    METRICS_CONTENT_TYPE,
    ConsumerMetrics,
    ReaperMetrics,
)
from queue_backend.pg_queue.reaper import (
    PgReaper,
    recover_expired_barriers,
    refresh_queue_gauges,
    sweep_orphan_claims,
)

from .test_pg_reaper import _FakeLease


# Same stubs as test_pg_reaper's autouse fixtures (they're module-local there):
# tick() also runs the scheduler dispatch + retention sweeps, which would
# otherwise hit the dummy injected sweep_conn.
@pytest.fixture(autouse=True)
def stub_scheduler_and_sweeps(monkeypatch):
    monkeypatch.setattr(reaper_mod, "dispatch_due_schedules", MagicMock(return_value=0))
    monkeypatch.setattr(reaper_mod, "sweep_expired_results", MagicMock(return_value=0))
    monkeypatch.setattr(reaper_mod, "sweep_orphan_dedup", MagicMock(return_value=0))
    monkeypatch.setattr(reaper_mod, "sweep_orphan_claims", MagicMock(return_value=0))


def _get(url: str):
    return urllib.request.urlopen(url, timeout=5)


def _sample(metrics, name: str, labels: dict[str, str] | None = None) -> float | None:
    return metrics.registry.get_sample_value(name, labels or {})


@contextlib.contextmanager
def _running(server):
    server.start()
    try:
        yield server
    finally:
        server.stop()


class TestLivenessMetricsRoute:
    """/metrics on the shared LivenessServer: opt-in, never touching /health."""

    def _server(self, metrics_fn) -> LivenessServer:
        return LivenessServer(
            freshness_fn=lambda: 0.0,
            stale_after=60,
            port=0,
            check_name="t",
            age_key="age",
            metrics_fn=metrics_fn,
        )

    def test_404_when_no_metrics_fn(self):
        with _running(self._server(None)) as server:
            with pytest.raises(urllib.error.HTTPError) as ei:
                _get(f"http://127.0.0.1:{server.bound_port}/metrics")
            assert ei.value.code == 404

    def test_serves_prometheus_body_and_content_type(self):
        with _running(self._server(lambda: b"pg_test_metric 1.0\n")) as server:
            with _get(f"http://127.0.0.1:{server.bound_port}/metrics") as resp:
                assert resp.status == 200
                assert resp.headers["Content-Type"] == METRICS_CONTENT_TYPE
                assert resp.read() == b"pg_test_metric 1.0\n"

    def test_query_string_is_stripped(self):
        # Mirrors the /health?probe=k8s behavior — self.path includes the query.
        with _running(self._server(lambda: b"x 1\n")) as server:
            with _get(
                f"http://127.0.0.1:{server.bound_port}/metrics?scrape=test"
            ) as resp:
                assert resp.status == 200

    def test_broken_metrics_fn_500s_but_health_still_answers(self):
        # The whole point of sharing the server: a broken exporter must degrade
        # to /metrics alone — the probe verdict is untouched.
        def boom() -> bytes:
            raise RuntimeError("render failed")

        with _running(self._server(boom)) as server:
            base = f"http://127.0.0.1:{server.bound_port}"
            with pytest.raises(urllib.error.HTTPError) as ei:
                _get(f"{base}/metrics")
            assert ei.value.code == 500
            with _get(f"{base}/health") as resp:
                assert resp.status == 200


class TestConsumerMetrics:
    def test_heartbeat_gauge_tracks_freshness_fn(self):
        age = 7.5
        metrics = ConsumerMetrics(freshness_fn=lambda: age)
        assert _sample(metrics, "pg_consumer_heartbeat_age_seconds") == pytest.approx(
            7.5
        )
        age = 42.0  # live callback, not a captured constant
        assert _sample(metrics, "pg_consumer_heartbeat_age_seconds") == pytest.approx(
            42.0
        )

    def test_fleet_hooks_are_optional(self):
        plain = ConsumerMetrics(freshness_fn=lambda: 0.0)
        assert _sample(plain, "pg_consumer_alive_children") is None

        fleet = ConsumerMetrics(
            freshness_fn=lambda: 0.0,
            alive_children_fn=lambda: 3.0,
            concurrency_fn=lambda: 4.0,
        )
        assert _sample(fleet, "pg_consumer_alive_children") == pytest.approx(3.0)
        assert _sample(fleet, "pg_consumer_configured_concurrency") == pytest.approx(
            4.0
        )

    def test_render_is_prometheus_exposition(self):
        body = ConsumerMetrics(freshness_fn=lambda: 1.0).render()
        assert b"pg_consumer_heartbeat_age_seconds" in body

    def test_two_instances_do_not_collide(self):
        # Instance registries: the workers tree can be imported under two module
        # names (bare-``tasks`` quirk), so module-level collectors would
        # double-register. Two instances must simply coexist.
        ConsumerMetrics(freshness_fn=lambda: 0.0)
        ConsumerMetrics(freshness_fn=lambda: 0.0)


def _reaper_metrics(*, leader: bool = True) -> ReaperMetrics:
    return ReaperMetrics(heartbeat_fn=lambda: 1.0, is_leader_fn=lambda: leader)


class TestReaperMetrics:
    def test_leadership_gauge(self):
        assert _sample(
            _reaper_metrics(leader=True), "pg_reaper_is_leader"
        ) == pytest.approx(1.0)
        assert _sample(
            _reaper_metrics(leader=False), "pg_reaper_is_leader"
        ) == pytest.approx(0.0)

    def test_snapshot_set_then_drained_queue_drops_out(self):
        metrics = _reaper_metrics()
        metrics.set_queue_snapshot(
            depths={"q1": (5, 120.0), "q2": (1, 3.0)},
            barriers_live=2,
            barriers_stranded=1,
        )
        assert _sample(metrics, "pg_queue_depth", {"queue": "q1"}) == pytest.approx(5.0)
        assert _sample(
            metrics, "pg_queue_oldest_message_age_seconds", {"queue": "q1"}
        ) == pytest.approx(120.0)
        assert _sample(metrics, "pg_barrier_live") == pytest.approx(2.0)
        assert _sample(metrics, "pg_barrier_stranded") == pytest.approx(1.0)

        # q1 drains: its series must DROP, not freeze at the last non-zero value.
        metrics.set_queue_snapshot(
            depths={"q2": (0, 0.0)}, barriers_live=0, barriers_stranded=0
        )
        assert _sample(metrics, "pg_queue_depth", {"queue": "q1"}) is None
        assert _sample(metrics, "pg_queue_depth", {"queue": "q2"}) == pytest.approx(0.0)

    def test_clear_drops_series_and_zeroes_barriers(self):
        # On losing leadership a standby must not export a frozen stale snapshot.
        metrics = _reaper_metrics()
        metrics.set_queue_snapshot(
            depths={"q": (9, 10.0)}, barriers_live=1, barriers_stranded=1
        )
        metrics.clear_queue_snapshot()
        assert _sample(metrics, "pg_queue_depth", {"queue": "q"}) is None
        assert _sample(metrics, "pg_barrier_live") == pytest.approx(0.0)

    def test_gauges_age_grows_when_never_refreshed(self):
        # The staleness metric must never report "fresh" in the maximal-staleness
        # case: with no snapshot ever taken it grows from construction, so a
        # leader whose refresh has failed since boot still trips an age alert.
        metrics = _reaper_metrics()
        age = _sample(metrics, "pg_queue_gauges_age_seconds")
        assert age is not None and age >= 0.0
        metrics._queue_collector._snapshot = (
            metrics._queue_collector._snapshot.__class__(
                reference_monotonic=metrics._queue_collector._snapshot.reference_monotonic
                - 100.0
            )
        )
        aged = _sample(metrics, "pg_queue_gauges_age_seconds")
        assert aged is not None and aged >= 100.0

    def test_gauges_age_resets_on_snapshot_and_on_clear(self):
        metrics = _reaper_metrics()
        metrics.set_queue_snapshot(depths={}, barriers_live=0, barriers_stranded=0)
        age = _sample(metrics, "pg_queue_gauges_age_seconds")
        assert age is not None and 0.0 <= age < 5.0
        # clear() restarts the age from the step-down instant (not from boot).
        metrics.clear_queue_snapshot()
        age = _sample(metrics, "pg_queue_gauges_age_seconds")
        assert age is not None and 0.0 <= age < 5.0

    def test_collector_describe_lists_names_without_samples(self):
        # Registration protocol: describe() must expose the same names as
        # collect() (registry duplicate-checking) but with NO samples — so
        # register() never runs the render path (clock read) as a side effect.
        metrics = _reaper_metrics()
        collector = metrics._queue_collector
        described = {m.name: m for m in collector.describe()}
        collected = {m.name for m in collector.collect()}
        assert set(described) == collected
        assert all(not m.samples for m in described.values())

    def test_scrape_is_atomic_snapshot(self):
        # The collector renders from ONE snapshot reference: a replace() during
        # a render can't mix old and new values. Simulate by capturing the
        # families from collect() and swapping mid-iteration.
        metrics = _reaper_metrics()
        metrics.set_queue_snapshot(
            depths={"q": (5, 50.0)}, barriers_live=5, barriers_stranded=5
        )
        collector = metrics._queue_collector
        families = list(collector.collect())  # snapshot read happens here
        metrics.set_queue_snapshot(
            depths={"q": (9, 90.0)}, barriers_live=9, barriers_stranded=9
        )
        by_name = {f.name: f for f in families}
        depth = by_name["pg_queue_depth"].samples[0].value
        live = by_name["pg_barrier_live"].samples[0].value
        assert (depth, live) == (pytest.approx(5.0), pytest.approx(5.0))


class _FakeCursor:
    """Cursor returning one preloaded result set per execute() call, recording
    each ``(sql, params)`` so tests can pin the SQL contract."""

    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self._current = None
        self.executed: list[tuple[str, object]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._current = self._result_sets.pop(0)

    def fetchall(self):
        return self._current

    def fetchone(self):
        return self._current

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, result_sets):
        self.cursor_obj = _FakeCursor(result_sets)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class TestRefreshQueueGauges:
    def test_snapshot_from_sql_rows(self):
        metrics = _reaper_metrics()
        conn = _FakeConn(
            [
                [("file_processing", 7, 33.0), ("celery", 0, 0.0)],  # depth rows
                (4, 2),  # barriers live, stranded
            ]
        )
        refresh_queue_gauges(conn, metrics, stuck_timeout_seconds=9000)
        assert conn.commits == 1
        assert _sample(
            metrics, "pg_queue_depth", {"queue": "file_processing"}
        ) == pytest.approx(7.0)
        assert _sample(metrics, "pg_barrier_live") == pytest.approx(4.0)
        assert _sample(metrics, "pg_barrier_stranded") == pytest.approx(2.0)

    def test_sql_contract(self):
        # Pin the queries: wrong table, dropped GROUP BY, a missing stranded
        # predicate or unbound stuck-timeout would silently diverge the metric
        # from what the reaper actually recovers.
        metrics = _reaper_metrics()
        conn = _FakeConn([[], (0, 0)])
        refresh_queue_gauges(conn, metrics, stuck_timeout_seconds=9000)
        (depth_sql, depth_params), (barrier_sql, barrier_params) = (
            conn.cursor_obj.executed
        )
        assert "pg_queue_message" in depth_sql
        assert "GROUP BY queue_name" in depth_sql
        assert depth_params is None
        assert "pg_barrier_state" in barrier_sql
        assert "remaining > 0" in barrier_sql
        assert reaper_mod._STRANDED_PREDICATE in barrier_sql
        assert barrier_params == (9000,)

    def test_error_rolls_back_and_reraises(self):
        metrics = _reaper_metrics()
        conn = MagicMock()
        conn.cursor.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            refresh_queue_gauges(conn, metrics, stuck_timeout_seconds=9000)
        conn.rollback.assert_called_once()
        # No partial snapshot: the depth series stay absent.
        assert _sample(metrics, "pg_queue_depth", {"queue": "any"}) is None


class TestOutcomeCounters:
    """The recovery/sweep functions increment counters at their summary sites."""

    def test_barrier_recovery_counts(self):
        metrics = _reaper_metrics()
        conn = _FakeConn([[("e1", "org", 1), ("e2", "org", 1)]])
        with patch.object(
            reaper_mod, "_recover_one_barrier", side_effect=[True, RuntimeError("x")]
        ):
            recovered = recover_expired_barriers(
                conn, api_client=object(), stuck_timeout_seconds=1, metrics=metrics
            )
        assert recovered == ["e1"]
        assert _sample(metrics, "pg_reaper_barrier_recovered_total") == pytest.approx(
            1.0
        )
        assert _sample(
            metrics, "pg_reaper_barrier_recovery_failures_total"
        ) == pytest.approx(1.0)

    def test_claim_sweep_counts(self):
        metrics = _reaper_metrics()
        conn = _FakeConn([[("e1", "org"), ("e2", "org")]])
        with patch.object(
            reaper_mod,
            "_recover_one_claim",
            side_effect=[reaper_mod._CLAIM_RECOVERED, reaper_mod._CLAIM_GC],
        ):
            removed = sweep_orphan_claims(
                conn, api_client=object(), stuck_timeout_seconds=1, metrics=metrics
            )
        assert removed == 2
        assert _sample(metrics, "pg_reaper_claim_recovered_total") == pytest.approx(1.0)
        assert _sample(metrics, "pg_reaper_claim_gc_total") == pytest.approx(1.0)
        assert _sample(
            metrics, "pg_reaper_claim_recovery_failures_total"
        ) == pytest.approx(0.0)

    def test_counters_optional_no_metrics_kwarg(self):
        # Celery-safety twin: existing callers that pass no metrics still work.
        conn = _FakeConn([[]])
        assert (
            recover_expired_barriers(conn, api_client=object(), stuck_timeout_seconds=1)
            == []
        )


class TestReaperTickWiring:
    def _reaper(self, lease, **kw) -> PgReaper:
        return PgReaper(
            lease, interval_seconds=0.01, sweep_conn=object(), api_client=object(), **kw
        )

    def test_leader_tick_refreshes_gauges(self):
        reaper = self._reaper(_FakeLease(acquires=True))
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            patch.object(reaper_mod, "refresh_queue_gauges") as refresh,
        ):
            reaper.tick()
        # Pin the args: the reaper must feed ITS OWN exporter with ITS timeout.
        refresh.assert_called_once_with(
            reaper._sweep_conn, reaper.metrics, reaper._stuck_timeout_seconds
        )

    def test_refresh_is_cadence_gated_and_resumes(self):
        reaper = self._reaper(_FakeLease(acquires=True))
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            patch.object(reaper_mod, "refresh_queue_gauges") as refresh,
        ):
            reaper.tick()
            reaper.tick()  # within the refresh interval → no second refresh
            assert refresh.call_count == 1
            # Resumption: once the interval elapses the gate must reopen —
            # otherwise gauges silently freeze forever after the first snapshot.
            reaper._last_gauge_refresh_monotonic -= (
                reaper_mod._GAUGE_REFRESH_INTERVAL_SECONDS + 1
            )
            reaper.tick()
            assert refresh.call_count == 2

    def test_refresh_failure_never_fails_the_tick_and_consumes_the_interval(self):
        reaper = self._reaper(_FakeLease(acquires=True))
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            patch.object(
                reaper_mod, "refresh_queue_gauges", side_effect=RuntimeError("db")
            ) as refresh,
        ):
            outcome = reaper.tick()  # must not raise
            assert outcome.was_leader is True
            # Cadence advanced BEFORE the failed read: the immediate next tick
            # must NOT retry (a persistent failure retries once per interval,
            # not every tick).
            reaper.tick()
            assert refresh.call_count == 1
        assert _sample(
            reaper.metrics, "pg_reaper_gauge_refresh_failures_total"
        ) == pytest.approx(1.0)

    def test_standby_never_refreshes(self):
        reaper = self._reaper(_FakeLease(acquires=False))
        with patch.object(reaper_mod, "refresh_queue_gauges") as refresh:
            reaper.tick()
        refresh.assert_not_called()

    def test_lost_leadership_clears_snapshot_and_resets_cadence(self):
        reaper = self._reaper(_FakeLease(acquires=[True, True], renews=[False, True]))
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            patch.object(reaper_mod, "refresh_queue_gauges") as refresh,
        ):
            reaper.tick()  # becomes leader, refresh #1
            reaper.metrics.set_queue_snapshot(
                depths={"q": (1, 1.0)}, barriers_live=1, barriers_stranded=0
            )
            reaper.tick()  # renew fails → steps down → snapshot cleared;
            # re-acquires within the same tick and refreshes IMMEDIATELY —
            # the cadence reset is load-bearing (else a re-elected leader
            # exports a false "empty queue" for up to a full interval).
            assert refresh.call_count == 2
        assert _sample(reaper.metrics, "pg_queue_depth", {"queue": "q"}) is None

    def test_renew_raise_clears_snapshot_before_propagating(self):
        # The OTHER step-down path: renew() raising (lost DB mid-lease). The
        # frozen snapshot must be cleared even though the tick re-raises.
        lease = _FakeLease(acquires=True)
        reaper = self._reaper(lease)
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            patch.object(reaper_mod, "refresh_queue_gauges"),
        ):
            reaper.tick()  # becomes leader
        reaper.metrics.set_queue_snapshot(
            depths={"q": (3, 1.0)}, barriers_live=1, barriers_stranded=0
        )
        lease.renew = MagicMock(side_effect=RuntimeError("db gone"))
        with pytest.raises(RuntimeError):
            reaper.tick()
        assert reaper.is_leader is False
        assert _sample(reaper.metrics, "pg_queue_depth", {"queue": "q"}) is None

    def test_sweep_failure_increments_labeled_counter(self, monkeypatch):
        reaper = self._reaper(_FakeLease(acquires=True))
        monkeypatch.setattr(
            reaper_mod, "sweep_expired_results", MagicMock(side_effect=OSError("db"))
        )
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            patch.object(reaper_mod, "refresh_queue_gauges"),
        ):
            reaper.tick()  # first leader tick sweeps immediately
        assert _sample(
            reaper.metrics, "pg_reaper_sweep_failures_total", {"table": "pg_task_result"}
        ) == pytest.approx(1.0)
        # A later successful sweep must NOT reset the counter (monotonic).
        monkeypatch.setattr(
            reaper_mod, "sweep_expired_results", MagicMock(return_value=0)
        )
        reaper._last_sweep_monotonic = None  # reopen the sweep cadence gate
        with (
            patch.object(reaper_mod, "recover_expired_barriers", return_value=[]),
            patch.object(reaper_mod, "refresh_queue_gauges"),
        ):
            reaper.tick()
        assert _sample(
            reaper.metrics, "pg_reaper_sweep_failures_total", {"table": "pg_task_result"}
        ) == pytest.approx(1.0)

    def test_run_counts_tick_failures(self):
        # The heartbeat is stamped at tick START, so /health stays 200 through
        # every-tick failures — this counter is the only machine-readable signal.
        reaper = self._reaper(_FakeLease(acquires=True))
        with patch.object(
            reaper_mod,
            "recover_expired_barriers",
            side_effect=RuntimeError("SELECT failed"),
        ):
            original_sleep = reaper_mod.time.sleep

            def stop_after_first(_secs):
                reaper._running = False
                original_sleep(0)

            with patch.object(reaper_mod.time, "sleep", side_effect=stop_after_first):
                reaper.run(install_signals=False)
        assert _sample(reaper.metrics, "pg_reaper_tick_failures_total") == pytest.approx(
            1.0
        )

    def test_metrics_served_on_liveness_port(self):
        # End-to-end: the reaper's /metrics answers with its registry content.
        from queue_backend.pg_queue.reaper import ReaperLivenessServer

        reaper = self._reaper(_FakeLease(acquires=True))
        with _running(ReaperLivenessServer(reaper, port=0, stale_after=60)) as server:
            with _get(f"http://127.0.0.1:{server.bound_port}/metrics") as resp:
                body = resp.read()
            assert b"pg_reaper_is_leader" in body
            assert b"pg_reaper_heartbeat_age_seconds" in body


class TestConsumerServerMetricsRoute:
    def test_consumer_metrics_served(self):
        from queue_backend.pg_queue.consumer import LivenessServer as ConsumerServer
        from queue_backend.pg_queue.consumer import PgQueueConsumer

        consumer = PgQueueConsumer(["q"], client=MagicMock())
        with _running(ConsumerServer(consumer, port=0, stale_after=60)) as server:
            with _get(f"http://127.0.0.1:{server.bound_port}/metrics") as resp:
                assert resp.headers["Content-Type"] == METRICS_CONTENT_TYPE
                assert b"pg_consumer_heartbeat_age_seconds" in resp.read()


class TestSupervisorMetricsRoute:
    def test_supervisor_fleet_metrics_served(self, monkeypatch):
        # The supervisor is the ONLY producer of the fleet gauges, and its
        # lambdas defer to scrape time — a _Fleet API rename would pass import
        # and 500 every scrape at runtime only. Exercise the real wiring.
        from pg_queue_consumer.supervisor import _Fleet, _maybe_start_supervisor_health

        monkeypatch.setenv("WORKER_PG_QUEUE_CONSUMER_HEALTH_PORT", "0")
        fleet = _Fleet(2)
        server = _maybe_start_supervisor_health(fleet)
        assert server is not None
        try:
            with _get(f"http://127.0.0.1:{server.bound_port}/metrics") as resp:
                body = resp.read()
            assert b"pg_consumer_heartbeat_age_seconds" in body
            assert b"pg_consumer_alive_children" in body
            assert b"pg_consumer_configured_concurrency 2.0" in body
        finally:
            server.stop()
