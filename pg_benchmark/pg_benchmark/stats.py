"""Pure latency statistics — no I/O, fully unit-testable.

The benchmark's headline output is a distribution, not a single number: a mean
hides the tail, and the tail is exactly where a polling transport (PG
SKIP-LOCKED) is suspected to differ from a push transport (RabbitMQ). So every
metric is summarised as ``n / mean / p50 / p95 / p99 / min / max / stdev``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Summary:
    """A latency distribution summary over a sample of measurements."""

    n: int
    mean: float
    p50: float
    p95: float
    p99: float
    minimum: float
    maximum: float
    stdev: float

    @property
    def empty(self) -> bool:
        return self.n == 0


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile (``pct`` in 0..100).

    Uses the same "linear interpolation between closest ranks" method as
    ``numpy.percentile`` / ``statistics.quantiles(method="inclusive")`` so the
    numbers line up with what an analyst expects, without pulling numpy in.
    """
    if not values:
        raise ValueError("percentile() of an empty sample")
    if pct <= 0:
        return min(values)
    if pct >= 100:
        return max(values)
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    frac = rank - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def summarize(values: list[float]) -> Summary:
    """Summarise a sample. An empty sample yields an all-zero ``Summary``."""
    n = len(values)
    if n == 0:
        return Summary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
    return Summary(
        n=n,
        mean=mean,
        p50=percentile(values, 50),
        p95=percentile(values, 95),
        p99=percentile(values, 99),
        minimum=min(values),
        maximum=max(values),
        stdev=math.sqrt(variance),
    )
