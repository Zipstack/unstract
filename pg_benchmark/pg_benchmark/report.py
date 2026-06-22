"""Aggregate executions by transport and render a PG-vs-Celery comparison.

The comparison is the point: same metric, side by side, per transport, so a
regression or win is visible at a glance rather than buried in two separate runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import ExecutionLatency, Transport
from .probe import RunResult
from .runner import LoadOutcome
from .stats import Summary, summarize


@dataclass(frozen=True, slots=True)
class TransportReport:
    """Per-transport rollup of a sample of executions."""

    transport: Transport
    count: int
    execution_time: Summary
    parallelism: Summary
    error_rate: float


def build_reports(executions: list[ExecutionLatency]) -> list[TransportReport]:
    """Group by transport and summarise execution-time + parallelism + errors."""
    reports: list[TransportReport] = []
    for transport in Transport:
        bucket = [e for e in executions if e.transport is transport]
        if not bucket:
            continue
        exec_times = [
            e.server_execution_time for e in bucket if e.server_execution_time is not None
        ]
        parallelisms = [e.parallelism for e in bucket if e.parallelism is not None]
        errors = sum(1 for e in bucket if e.status == "ERROR")
        reports.append(
            TransportReport(
                transport=transport,
                count=len(bucket),
                execution_time=summarize(exec_times),
                parallelism=summarize(parallelisms),
                error_rate=errors / len(bucket),
            )
        )
    return reports


@dataclass(frozen=True, slots=True)
class LoadReport:
    """Per-transport rollup of a controlled load run."""

    transport: Transport
    triggered: int
    completed: int
    failed: int
    wall_clock_e2e: Summary
    server_execution_time: Summary
    overhead: Summary
    http_latency: Summary


def build_load_reports(results: list[RunResult]) -> list[LoadReport]:
    """Group probe results by observed transport and summarise each metric."""
    reports: list[LoadReport] = []
    # ``None`` transport bucket = runs that never produced a classifiable row.
    transports: list[Transport | None] = [*Transport, None]
    for transport in transports:
        bucket = [r for r in results if r.transport is transport]
        if not bucket:
            continue
        completed = [r for r in bucket if r.ok]
        reports.append(
            LoadReport(
                transport=transport or Transport.INLINE,
                triggered=len(bucket),
                completed=len(completed),
                failed=len(bucket) - len(completed),
                wall_clock_e2e=summarize(
                    [r.wall_clock_e2e for r in bucket if r.wall_clock_e2e is not None]
                ),
                server_execution_time=summarize(
                    [
                        r.server_execution_time
                        for r in bucket
                        if r.server_execution_time is not None
                    ]
                ),
                overhead=summarize(
                    [r.overhead for r in bucket if r.overhead is not None]
                ),
                http_latency=summarize([r.http_latency for r in bucket]),
            )
        )
    return reports


def render_load(outcome: LoadOutcome) -> str:
    """Render a load run: throughput headline + per-transport latency tables."""
    reports = build_load_reports(outcome.results)
    lines = [
        f"Load run: {len(outcome.results)} triggered, "
        f"{len(outcome.completed)} completed in {outcome.wall_clock:.1f}s "
        f"→ {outcome.throughput:.2f} completed/s",
        "",
    ]
    if not reports:
        lines.append("No results.")
        return "\n".join(lines)
    for r in reports:
        lines.append(
            f"── {r.transport.value.upper()}  "
            f"({r.completed}/{r.triggered} ok, {r.failed} failed) ".ljust(78, "─")
        )
        lines.append(f"  wall-clock e2e (s): {_fmt(r.wall_clock_e2e)}")
        lines.append(f"  server exec  (s)  : {_fmt(r.server_execution_time)}")
        lines.append(f"  overhead     (s)  : {_fmt(r.overhead)}")
        lines.append(f"  http trigger (s)  : {_fmt(r.http_latency)}")
        lines.append("")
    return "\n".join(lines)


def _fmt(summary: Summary) -> str:
    if summary.empty:
        return "       (no samples)"
    return (
        f"n={summary.n:<4} mean={summary.mean:7.2f}  p50={summary.p50:7.2f}  "
        f"p95={summary.p95:7.2f}  p99={summary.p99:7.2f}  max={summary.maximum:7.2f}"
    )


def render(reports: list[TransportReport]) -> str:
    """Render reports as a human-readable text block."""
    if not reports:
        return "No executions matched the query."
    lines: list[str] = []
    for r in reports:
        lines.append(
            f"── {r.transport.value.upper()}  ({r.count} executions, "
            f"error_rate={r.error_rate:.1%}) ".ljust(78, "─")
        )
        lines.append(f"  execution_time (s): {_fmt(r.execution_time)}")
        para = r.parallelism
        if para.empty:
            lines.append("  parallelism       :        (single-file or untimed)")
        else:
            lines.append(
                f"  parallelism (x)   : mean={para.mean:5.2f}  p50={para.p50:5.2f}  "
                f"min={para.minimum:5.2f}  max={para.maximum:5.2f}  "
                f"(≈1 serial, ≈N fully parallel)"
            )
        lines.append("")
    return "\n".join(lines)
