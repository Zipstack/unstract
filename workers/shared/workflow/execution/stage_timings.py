"""Per-stage timing capture for a single file's workflow execution.

Collects the durations of a file's pipeline stages (setup, source fetch, tool
execution, destination, finalization) into a payload that is sent with the
terminal status update and persisted on
``WorkflowFileExecution.stage_timings``.

Queue wait is deliberately *not* measured here: the worker has no view of when
the file execution row was created, so the collector reports ``started_at`` and
the backend derives ``queue_wait`` from ``created_at``. ``started_at`` must
share its anchor with the ``execution_time`` the backend persists, or the gap
between the two readings is counted in both.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from shared.infrastructure.logging import WorkerLogger

from unstract.core.stage_timings import (
    STAGE_TIMINGS_VERSION,
    ToolStage,
    WorkflowStage,
    coerce_seconds,
)

logger = WorkerLogger.get_logger(__name__)

__all__ = [
    "STAGE_TIMINGS_VERSION",
    "StageTimingCollector",
    "ToolStage",
    "WorkflowStage",
    "tool_split_from_metrics",
]

# Keys inside the structure tool's ``metrics`` dict. Mirrors
# executor.executors.constants.PromptServiceConstants, duplicated here because
# this module is imported by the workflow-execution service, which must not
# depend on the executor package.
_FILE_METRICS_KEY = "_file"
_TEXT_EXTRACTION_KEY = "text_extraction"
_INDEXING_KEY = "indexing"
_TIME_TAKEN_KEY = "time_taken(s)"


def _sum_time_taken(node: Any) -> float:
    """Recursively sum every ``time_taken(s)`` under ``node``.

    Plugin metrics (table / line-item extraction) nest arbitrarily deep and
    their shape is owned by the plugin, so walking is more durable than
    enumerating keys.
    """
    if not isinstance(node, dict):
        return 0.0
    total = 0.0
    for key, value in node.items():
        if key == _TIME_TAKEN_KEY:
            total += coerce_seconds(value)
        else:
            total += _sum_time_taken(value)
    return total


def tool_split_from_metrics(
    metrics: Any, agentic_extraction_seconds: float = 0.0
) -> dict[str, float]:
    """Split the structure tool's ``metrics`` dict into extraction/indexing/prompts.

    Per-prompt figures are summed — the ticket asks for a stage split, not a
    per-prompt one.

    Args:
        metrics: ``structured_output["metrics"]`` from the structure tool.
        agentic_extraction_seconds: Seconds that
            ``structure_tool_task._merge_agentic_metrics`` folded out of the
            agentic prompt buckets into the file-level extraction bucket. That
            time appears in both places, so it is subtracted from ``prompts``
            once here. Passing the exact amount is what keeps this correct:
            excluding every sub-tree *named* ``text_extraction`` instead would
            also silently drop the non-agentic table plugin's own extraction
            time, which was never folded and belongs in ``prompts``.

    Returns:
        Seconds per tool sub-stage. Empty when ``metrics`` carries no timings,
        so a Docker (non-structure) tool reports no split rather than zeros.
    """
    if not isinstance(metrics, dict) or not metrics:
        return {}

    file_metrics = metrics.get(_FILE_METRICS_KEY)
    extraction = 0.0
    if isinstance(file_metrics, dict):
        extraction = _sum_time_taken(file_metrics.get(_TEXT_EXTRACTION_KEY))

    indexing = 0.0
    prompts = 0.0
    for key, prompt_metrics in metrics.items():
        if key == _FILE_METRICS_KEY or not isinstance(prompt_metrics, dict):
            continue
        for sub_key, entry in prompt_metrics.items():
            if sub_key == _INDEXING_KEY:
                indexing += _sum_time_taken(entry)
            else:
                prompts += _sum_time_taken(entry)

    prompts = max(prompts - coerce_seconds(agentic_extraction_seconds), 0.0)

    split = {
        ToolStage.EXTRACTION: extraction,
        ToolStage.INDEXING: indexing,
        ToolStage.PROMPTS: prompts,
    }
    return {k: round(v, 3) for k, v in split.items() if v > 0}


class StageTimingCollector:
    """Accumulates per-stage durations for one file execution.

    Every method swallows its own errors: timing is diagnostic, and a bad
    measurement must never fail an execution that otherwise succeeded.
    """

    def __init__(self, started_at: float | None = None) -> None:
        self._started_at = started_at if started_at is not None else time.time()
        self._stages: dict[str, float] = {}
        self._tool_split: dict[str, float] = {}

    @property
    def started_at(self) -> float:
        return self._started_at

    def record(self, stage: str, seconds: float) -> None:
        """Add ``seconds`` to ``stage``, accumulating across repeat calls."""
        value = coerce_seconds(seconds)
        self._stages[stage] = round(self._stages.get(stage, 0.0) + value, 3)

    def record_span(self, stage: str, start: float, end: float) -> None:
        """Record a stage from two ``time.time()`` readings."""
        self.record(stage, end - start)

    @contextmanager
    def stage(self, stage: str) -> Iterator[None]:
        """Time a block as ``stage``, including when it raises.

        A stage that fails part-way still took the time it took, and that is
        exactly the number someone debugging a slow failure wants.
        """
        start = time.time()
        try:
            yield
        finally:
            self.record(stage, time.time() - start)

    def set_tool_split(
        self, metrics: Any, agentic_extraction_seconds: float = 0.0
    ) -> None:
        """Derive the tool sub-stage split from the structure tool's metrics."""
        try:
            split = tool_split_from_metrics(metrics, agentic_extraction_seconds)
        except Exception:
            logger.warning("Failed to derive tool stage split", exc_info=True)
            return
        for key, value in split.items():
            self._tool_split[key] = round(self._tool_split.get(key, 0.0) + value, 3)

    def to_dict(self, total: float | None = None) -> dict[str, Any]:
        """Build the persisted payload.

        Args:
            total: Wall-clock seconds the worker spent on this file. Defaults
                to the span since the collector was created.

        Returns:
            The ``stage_timings`` payload. ``queue_wait`` is absent — the
            backend adds it from ``created_at``.
        """
        try:
            measured_total = (
                coerce_seconds(total)
                if total is not None
                else max(time.time() - self._started_at, 0.0)
            )
            accounted = sum(self._stages.values())
            payload: dict[str, Any] = {
                "version": STAGE_TIMINGS_VERSION,
                "started_at": round(self._started_at, 6),
                "total": round(measured_total, 3),
                "stages": dict(self._stages),
            }
            if self._tool_split:
                payload["tool_split"] = dict(self._tool_split)
            # Negative would mean the stages overlap or outran the total;
            # report nothing rather than a number that cannot be true.
            unaccounted = round(measured_total - accounted, 3)
            if unaccounted > 0:
                payload["unaccounted"] = unaccounted
            return payload
        except Exception:
            logger.warning("Failed to build stage timings payload", exc_info=True)
            return {}
