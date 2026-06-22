"""Concurrent load runner: drive N probes at concurrency C.

A fixed-size thread pool keeps exactly ``concurrency`` executions in flight at
once (the probes are I/O-bound — HTTP + DB polling — so threads are the right
tool). Each probe is independent and owns its own connections, so failures are
isolated: one bad run becomes one ``RunResult`` with ``ok=False``, never a dead
batch.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .config import DbConfig
from .probe import RunResult, run_probe
from .trigger import TriggerConfig


@dataclass(frozen=True, slots=True)
class LoadOutcome:
    """The full result set of a load run plus its wall-clock + throughput."""

    results: list[RunResult]
    wall_clock: float  # total seconds for the whole batch

    @property
    def completed(self) -> list[RunResult]:
        return [r for r in self.results if r.ok]

    @property
    def throughput(self) -> float:
        """Completed executions per second over the batch wall-clock."""
        if self.wall_clock <= 0:
            return 0.0
        return len(self.completed) / self.wall_clock


def run_load(
    trigger_cfg: TriggerConfig,
    db_cfg: DbConfig,
    *,
    n: int,
    concurrency: int,
    poll_interval: float = 0.5,
    timeout: float = 600.0,
    on_result: Callable[[RunResult], None] | None = None,
    probe: Callable[..., RunResult] = run_probe,
) -> LoadOutcome:
    """Run ``n`` probes, at most ``concurrency`` at a time.

    ``on_result`` (optional) is called as each probe finishes — used by the CLI
    to stream progress. ``probe`` is injectable so the runner is unit-testable
    without HTTP/DB.
    """
    results: list[RunResult] = []
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                probe,
                trigger_cfg,
                db_cfg,
                poll_interval=poll_interval,
                timeout=timeout,
            )
            for _ in range(n)
        ]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if on_result is not None:
                on_result(result)
    return LoadOutcome(results=results, wall_clock=time.monotonic() - start)
