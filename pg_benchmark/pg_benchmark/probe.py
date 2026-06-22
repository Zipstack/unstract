"""One full execution probe: trigger → poll to terminal → read server latency.

Combines the two clocks the benchmark cares about:

- **client wall-clock** (``http_latency``, ``wall_clock_e2e``) — what a caller
  feels, including queue wait + dispatch + poll granularity
- **server-measured** (``server_execution_time``, ``parallelism``) — the
  transport-fair number, read from the DB by ``execution_id``

``overhead = wall_clock_e2e - server_execution_time`` is the part the transport
is responsible for (admission + queue wait + result delivery); it is where a
polling vs push transport would diverge.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import requests

from .config import DbConfig
from .db import Transport, connect, fetch_one, fetch_status, is_terminal_status
from .trigger import TriggerConfig, trigger_execution


@dataclass(frozen=True, slots=True)
class RunResult:
    """Everything measured for one execution probe."""

    execution_id: str | None
    transport: Transport | None
    status: str | None
    ok: bool
    http_latency: float
    wall_clock_e2e: float | None
    server_execution_time: float | None
    parallelism: float | None
    overhead: float | None
    error: str | None = None


def run_probe(
    trigger_cfg: TriggerConfig,
    db_cfg: DbConfig,
    *,
    poll_interval: float = 0.5,
    timeout: float = 600.0,
    session: requests.Session | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> RunResult:
    """Trigger one execution and measure it end to end.

    ``clock``/``sleep`` are injected so the poll loop is unit-testable without
    real time. Each probe owns its own DB connection (psycopg2 connections are
    not safe to share across the load runner's threads).
    """
    start = clock()
    trig = trigger_execution(trigger_cfg, session)
    if trig.execution_id is None:
        return RunResult(
            execution_id=None,
            transport=None,
            status=None,
            ok=False,
            http_latency=trig.http_latency,
            wall_clock_e2e=None,
            server_execution_time=None,
            parallelism=None,
            overhead=None,
            error=trig.error or "trigger returned no execution_id",
        )

    conn = connect(db_cfg)
    try:
        deadline = start + timeout
        status: str | None = None
        while clock() < deadline:
            status = fetch_status(conn, trig.execution_id)
            if is_terminal_status(status):
                break
            sleep(poll_interval)
        wall_clock_e2e = clock() - start
        latency = fetch_one(conn, trig.execution_id)
    finally:
        conn.close()

    if not is_terminal_status(status):
        return RunResult(
            execution_id=trig.execution_id,
            transport=latency.transport if latency else None,
            status=status,
            ok=False,
            http_latency=trig.http_latency,
            wall_clock_e2e=wall_clock_e2e,
            server_execution_time=latency.server_execution_time if latency else None,
            parallelism=latency.parallelism if latency else None,
            overhead=None,
            error=f"timed out after {timeout:.0f}s (last status={status})",
        )

    server_time = latency.server_execution_time if latency else None
    overhead = (
        wall_clock_e2e - server_time
        if server_time is not None and wall_clock_e2e is not None
        else None
    )
    return RunResult(
        execution_id=trig.execution_id,
        transport=latency.transport if latency else None,
        status=status,
        ok=status == "COMPLETED",
        http_latency=trig.http_latency,
        wall_clock_e2e=wall_clock_e2e,
        server_execution_time=server_time,
        parallelism=latency.parallelism if latency else None,
        overhead=overhead,
        error=None if status == "COMPLETED" else f"terminal status={status}",
    )
