"""Unit tests for the load layer (probe / runner / load report) with fakes.

No HTTP or DB: ``run_probe``'s collaborators (trigger + DB readers) are
monkeypatched, and the poll loop's clock/sleep are injected, so the timing logic
is exercised deterministically.
"""

from __future__ import annotations

import pytest

import pg_benchmark.probe as probe_mod
from pg_benchmark.config import DbConfig
from pg_benchmark.db import ExecutionLatency, Transport
from pg_benchmark.probe import RunResult, run_probe
from pg_benchmark.report import build_load_reports, render_load
from pg_benchmark.runner import LoadOutcome, run_load
from pg_benchmark.trigger import TriggerConfig, TriggerResult


class FakeClock:
    """Returns successive values, repeating the last once exhausted."""

    def __init__(self, values):
        self._values = list(values)
        self._i = 0

    def __call__(self):
        v = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return v


def _trigger_cfg():
    return TriggerConfig(base_url="http://x", path="/p/", api_key="k")


def _db_cfg():
    return DbConfig()


def _latency(transport=Transport.PG, status="COMPLETED", exec_time=30.0, files=(29.0,)):
    return ExecutionLatency(
        execution_id="e1",
        transport=transport,
        status=status,
        total_files=len(files),
        server_execution_time=exec_time,
        file_times=list(files),
    )


def _patch_probe(monkeypatch, *, trigger, statuses, latency):
    monkeypatch.setattr(probe_mod, "trigger_execution", lambda cfg, session=None: trigger)
    monkeypatch.setattr(probe_mod, "connect", lambda cfg: object())
    status_iter = iter(statuses)
    monkeypatch.setattr(
        probe_mod, "fetch_status", lambda conn, eid: next(status_iter, statuses[-1])
    )
    monkeypatch.setattr(probe_mod, "fetch_one", lambda conn, eid: latency)
    # connect() returns a bare object(); ensure .close() is a no-op
    monkeypatch.setattr(
        probe_mod, "connect", lambda cfg: type("C", (), {"close": lambda s: None})()
    )


class TestRunProbe:
    def test_success_computes_overhead(self, monkeypatch):
        trig = TriggerResult(execution_id="e1", http_status=200, http_latency=0.05)
        _patch_probe(
            monkeypatch,
            trigger=trig,
            statuses=["EXECUTING", "COMPLETED"],
            latency=_latency(exec_time=30.0),
        )
        clock = FakeClock([100.0, 100.1, 100.2, 130.6])  # wall = 30.6s
        result = run_probe(
            _trigger_cfg(),
            _db_cfg(),
            poll_interval=0.0,
            clock=clock,
            sleep=lambda s: None,
        )
        assert result.ok
        assert result.transport is Transport.PG
        assert result.wall_clock_e2e == pytest.approx(30.6)
        assert result.server_execution_time == 30.0
        assert result.overhead == pytest.approx(0.6)
        assert result.http_latency == 0.05

    def test_trigger_without_execution_id_is_failure(self, monkeypatch):
        trig = TriggerResult(
            execution_id=None, http_status=401, http_latency=0.02, error="HTTP 401"
        )
        _patch_probe(monkeypatch, trigger=trig, statuses=["x"], latency=None)
        result = run_probe(_trigger_cfg(), _db_cfg(), clock=FakeClock([1.0]))
        assert not result.ok
        assert result.execution_id is None
        assert "401" in result.error

    def test_timeout_when_never_terminal(self, monkeypatch):
        trig = TriggerResult(execution_id="e1", http_status=200, http_latency=0.05)
        _patch_probe(
            monkeypatch,
            trigger=trig,
            statuses=["EXECUTING"],
            latency=_latency(status="EXECUTING", exec_time=None, files=()),
        )
        # deadline = start + timeout = 100 + 1 = 101; clock crosses it immediately.
        clock = FakeClock([100.0, 102.0, 102.0])
        result = run_probe(
            _trigger_cfg(),
            _db_cfg(),
            timeout=1.0,
            clock=clock,
            sleep=lambda s: None,
        )
        assert not result.ok
        assert "timed out" in result.error
        assert result.overhead is None

    def test_error_status_is_not_ok(self, monkeypatch):
        trig = TriggerResult(execution_id="e1", http_status=200, http_latency=0.05)
        _patch_probe(
            monkeypatch,
            trigger=trig,
            statuses=["ERROR"],
            latency=_latency(status="ERROR"),
        )
        clock = FakeClock([100.0, 100.1, 130.0])
        result = run_probe(
            _trigger_cfg(),
            _db_cfg(),
            clock=clock,
            sleep=lambda s: None,
        )
        assert not result.ok
        assert result.status == "ERROR"


class TestRunner:
    def _result(self, ok=True, transport=Transport.PG, wall=10.0):
        return RunResult(
            execution_id="e",
            transport=transport,
            status="COMPLETED" if ok else "ERROR",
            ok=ok,
            http_latency=0.05,
            wall_clock_e2e=wall,
            server_execution_time=9.0,
            parallelism=1.8,
            overhead=wall - 9.0,
            error=None if ok else "err",
        )

    def test_run_load_collects_all_and_computes_throughput(self):
        calls = {"n": 0}

        def fake_probe(tcfg, dcfg, **kw):
            calls["n"] += 1
            return self._result(ok=calls["n"] % 2 == 1)

        outcome = run_load(
            _trigger_cfg(),
            _db_cfg(),
            n=4,
            concurrency=2,
            probe=fake_probe,
        )
        assert len(outcome.results) == 4
        assert len(outcome.completed) == 2
        assert outcome.throughput >= 0.0

    def test_load_outcome_zero_walltime_is_safe(self):
        outcome = LoadOutcome(results=[self._result()], wall_clock=0.0)
        assert outcome.throughput == 0.0


class TestLoadReport:
    def _result(self, transport, ok=True, wall=10.0, server=9.0):
        return RunResult(
            execution_id="e",
            transport=transport,
            status="COMPLETED" if ok else "ERROR",
            ok=ok,
            http_latency=0.05,
            wall_clock_e2e=wall,
            server_execution_time=server,
            parallelism=1.8,
            overhead=wall - server,
            error=None,
        )

    def test_groups_by_transport(self):
        results = [
            self._result(Transport.PG),
            self._result(Transport.PG, ok=False),
            self._result(Transport.CELERY),
        ]
        reports = build_load_reports(results)
        by_t = {r.transport: r for r in reports}
        assert by_t[Transport.PG].triggered == 2
        assert by_t[Transport.PG].completed == 1
        assert by_t[Transport.PG].failed == 1
        assert by_t[Transport.CELERY].triggered == 1

    def test_render_load_smoke(self):
        outcome = LoadOutcome(results=[self._result(Transport.PG)], wall_clock=10.0)
        text = render_load(outcome)
        assert "Load run" in text
        assert "PG" in text
        assert "wall-clock e2e" in text
