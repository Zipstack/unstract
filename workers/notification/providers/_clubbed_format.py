"""Worker-side mirror of backend/notification_v2/clubbed_renderer.

Producing the same envelope shape and Slack mrkdwn body the backend renders
so worker-callback IMMEDIATE payloads (flat per-event dicts) match the
canonical wire format used by backend BATCHED dispatches. Backend pre-renders
for its own dispatches — this module covers only the worker-callback IMMEDIATE
path. Keep the constants and string output byte-identical to
`backend/notification_v2/clubbed_renderer.py`; promote to `unstract/core/` if
a third site ever needs the same logic.
"""

from __future__ import annotations

import datetime
from typing import Any

MAX_BATCH_SIZE = 500
SLACK_MAX_DISPLAY_EVENTS = 25

_SUCCESS_STATUSES = {"COMPLETED", "SUCCESS"}
_SEPARATOR = " · "
_MISSING = "—"
_DIVIDER = "———"
_EMOJI_SUCCESS = ":white_check_mark:"
_EMOJI_FAILURE = ":x:"


def _is_success(status: str | None) -> bool:
    if not status:
        return False
    return status.upper() in _SUCCESS_STATUSES


def _humanize_timestamp(iso: str | None) -> str:
    if not iso:
        return _MISSING
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return _MISSING
    return dt.strftime("%Y %b %-d %I:%M:%S %p")


def _format_file_count(event: dict[str, Any]) -> str:
    counts = event.get("additional_data") or {}
    total = counts.get("total_files")
    if total is None:
        return ""
    if _is_success(event.get("status")):
        successful = counts.get("successful_files", 0)
        return f"{_EMOJI_SUCCESS} {successful}/{total} files"
    failed = counts.get("failed_files", 0)
    return f"{_EMOJI_FAILURE} {failed}/{total} files"


def _format_event_line(event: dict[str, Any]) -> str:
    parts = [
        _humanize_timestamp(event.get("timestamp")),
        f"*{event.get('execution_id') or _MISSING}*",
        event.get("type") or _MISSING,
        event.get("pipeline_name") or _MISSING,
        event.get("status") or _MISSING,
    ]
    file_count = _format_file_count(event)
    if file_count:
        parts.append(file_count)
    return _SEPARATOR.join(parts)


def _event_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project a flat per-event payload into the canonical shape.

    Drops `pipeline_id` and `_source` — neither appears in receiver-visible
    output. Mirrors the backend projection so renderer input is identical.
    """
    event: dict[str, Any] = {
        "type": payload.get("type") or "",
        "pipeline_name": payload.get("pipeline_name") or "",
        "status": payload.get("status") or "",
        "execution_id": payload.get("execution_id") or "",
        "timestamp": payload.get("timestamp") or "",
        "additional_data": payload.get("additional_data") or {},
    }
    error_message = payload.get("error_message")
    if error_message:
        event["error_message"] = error_message
    return event


def build_envelope(
    payloads: list[dict[str, Any]],
    interval_seconds: int | None,
) -> dict[str, Any]:
    """Build the canonical `{summary, events}` envelope.

    `interval_seconds=None` for IMMEDIATE -> `summary.interval_minutes` null.
    """
    capped = payloads[:MAX_BATCH_SIZE]
    succeeded = sum(1 for p in capped if _is_success(p.get("status")))
    failed = len(capped) - succeeded
    interval_minutes: int | None
    if interval_seconds is None:
        interval_minutes = None
    else:
        interval_minutes = max(1, interval_seconds // 60)
    return {
        "summary": {
            "total": len(capped),
            "succeeded": succeeded,
            "failed": failed,
            "interval_minutes": interval_minutes,
        },
        "events": [_event_from_payload(p) for p in capped],
    }


def render_slack_text(envelope: dict[str, Any]) -> str:
    """Render the envelope as Slack mrkdwn body text.

    Always emits header + divider regardless of event count so IMMEDIATE,
    BATCHED N=1, and BATCHED N>1 all share the same shape.
    """
    summary = envelope["summary"]
    events: list[dict[str, Any]] = envelope["events"]
    total = summary["total"]
    noun = "execution" if total == 1 else "executions"
    header = (
        f"*{total} {noun}* "
        f"({_EMOJI_SUCCESS} {summary['succeeded']} succeeded  "
        f"{_EMOJI_FAILURE} {summary['failed']} failed)"
    )
    visible = events[:SLACK_MAX_DISPLAY_EVENTS]
    sections: list[str] = [header, _DIVIDER]
    sections.extend(_format_event_line(e) for e in visible)
    overflow = len(events) - len(visible)
    if overflow > 0:
        sections.append(_DIVIDER)
        sections.append(f"_… and {overflow} more executions_")
    return "\n".join(sections)
