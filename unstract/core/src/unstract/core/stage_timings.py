"""Stage keys for the per-file execution timing breakdown (UN-3451).

Shared between the worker that measures the stages and the backend that
persists them on ``WorkflowFileExecution.stage_timings`` and serves them to the
execution-logs UI and API deployment responses.

Payload shape::

    {
        "version": 1,
        "total": 22.76,  # queue_wait + execution_time, set by the backend
        "stages": {
            "queue_wait": 1.42,  # added by the backend from created_at
            "setup": 0.31,
            "source_fetch": 0.88,
            "tool_execution": 18.42,
            "destination": 0.27,
            "finalization": 0.04,
        },
        "tool_split": {"extraction": 8.92, "indexing": 3.1, "prompts": 6.4},
        "unaccounted": 0.0,
    }

``total`` spans everything ``stages`` holds, so readers can divide by it. It is
*not* ``WorkflowFileExecution.execution_time``, which covers processing only
and therefore excludes ``queue_wait``.

Keys are absent rather than zero when a stage did not run, so a Docker
(non-structure) tool reports no ``tool_split`` instead of a split of zeros.
"""

# Payload schema version. Bump when the shape changes so readers can tell
# old rows from new ones.
STAGE_TIMINGS_VERSION = 1

# Key under the structure tool's output ``metadata`` carrying the seconds that
# ``_merge_agentic_metrics`` folded out of the agentic prompt buckets into the
# file-level extraction bucket. The split subtracts this exact amount rather
# than pattern-matching key names, so the non-agentic table plugin's own
# extraction time (never folded) is not silently dropped.
AGENTIC_EXTRACTION_SECONDS_KEY = "agentic_extraction_seconds"


class WorkflowStage:
    """Keys of the ``stages`` map, in the order they occur."""

    QUEUE_WAIT = "queue_wait"
    SETUP = "setup"
    SOURCE_FETCH = "source_fetch"
    TOOL_EXECUTION = "tool_execution"
    DESTINATION = "destination"
    FINALIZATION = "finalization"


class ToolStage:
    """Keys of the ``tool_split`` map — the tool_execution stage broken down."""

    EXTRACTION = "extraction"
    INDEXING = "indexing"
    PROMPTS = "prompts"


# Canonical display order. Readers should render known stages in this order and
# append any key they do not recognise, so an older UI stays correct against a
# newer payload.
STAGE_ORDER = (
    WorkflowStage.QUEUE_WAIT,
    WorkflowStage.SETUP,
    WorkflowStage.SOURCE_FETCH,
    WorkflowStage.TOOL_EXECUTION,
    WorkflowStage.DESTINATION,
    WorkflowStage.FINALIZATION,
)

TOOL_STAGE_ORDER = (
    ToolStage.EXTRACTION,
    ToolStage.INDEXING,
    ToolStage.PROMPTS,
)


def coerce_seconds(value) -> float:
    """Return ``value`` as float seconds, or 0.0 when it isn't usable.

    Rejects bools (``True`` is an ``int`` to Python, but never a duration) and
    negatives, which no measured span can be.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    if value < 0:
        return 0.0
    return float(value)


def _is_usable_seconds(value) -> bool:
    """Whether ``value`` is a number a duration could legitimately be."""
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value >= 0


def _add_seconds(target: dict, key: str, value) -> None:
    """Accumulate ``value`` into ``target[key]`` when it is a usable number.

    An unusable value is skipped entirely rather than counted as zero, so a
    malformed row cannot invent a stage that never ran.
    """
    if _is_usable_seconds(value):
        target[key] = target.get(key, 0.0) + float(value)


def aggregate_stage_timings(payloads) -> dict:
    """Sum per-file stage timings into one execution-level breakdown.

    Stage times across files are *summed*, not averaged: files run
    concurrently, so the result is total time spent in each stage across the
    execution, which is the figure that answers "where did the time go".
    It is deliberately not comparable to the execution's wall-clock duration.

    Args:
        payloads: Iterable of per-file ``stage_timings`` dicts. Entries that
            are missing or malformed are skipped.

    Returns:
        ``{"version", "files", "stages", "tool_split", "total"}``, or ``{}``
        when no payload carried any timing.
    """
    stages: dict = {}
    tool_split: dict = {}
    files = 0
    total = 0.0

    for payload in payloads or ():
        if not isinstance(payload, dict):
            continue
        payload_stages = payload.get("stages")
        payload_split = payload.get("tool_split")
        if not isinstance(payload_stages, dict) and not isinstance(payload_split, dict):
            continue
        files += 1
        if isinstance(payload_stages, dict):
            for key, value in payload_stages.items():
                _add_seconds(stages, key, value)
        if isinstance(payload_split, dict):
            for key, value in payload_split.items():
                _add_seconds(tool_split, key, value)
        payload_total = payload.get("total")
        if (
            isinstance(payload_total, (int, float))
            and not isinstance(payload_total, bool)
            and payload_total > 0
        ):
            total += float(payload_total)

    if not files:
        return {}

    result = {
        "version": STAGE_TIMINGS_VERSION,
        "files": files,
        "stages": {k: round(v, 3) for k, v in stages.items()},
        "total": round(total, 3),
    }
    if tool_split:
        result["tool_split"] = {k: round(v, 3) for k, v in tool_split.items()}
    return result
