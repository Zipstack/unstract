"""Canonical envelope + renderer for every dispatch — IMMEDIATE and BATCHED.

The same envelope shape feeds every channel × mode cell so receivers never
need to branch on "is this batched?":

    {
        "summary": {"total": N, "succeeded": S, "failed": F},
        "events": [
            {
                "type": "ETL" | "TASK" | "API",
                "pipeline_name": "...",
                "status": "ERROR" | "SUCCESS" | ...,
                "execution_id": "...",
                "timestamp": "2026 May 5 5:03:34 PM",
                "additional_data": {
                    "total_files": int,
                    "successful_files": int,
                    "failed_files": int,
                },
                "error_message": "...",   # only on failure
            },
            ...
        ]
    }

Slack receives `{"text": "<mrkdwn>"}` pre-rendered from this envelope; API
receivers see the envelope unchanged so programmatic consumers always parse
the same shape. `pipeline_id` is intentionally absent from every event dict.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from notification_v2.enums import PlatformType

logger = logging.getLogger(__name__)

# Hard cap on events per dispatch; the rest roll into the next flush tick.
MAX_BATCH_SIZE = 500
# Slack inlines this many events before collapsing the rest under an
# "_… and K more_" footer. Slack tolerates much larger payloads, but
# readability tanks past ~25 lines.
SLACK_MAX_DISPLAY_EVENTS = 25

_SUCCESS_STATUSES = {"COMPLETED", "SUCCESS"}

# Middle dot (U+00B7) padded by single spaces — the per-event field separator.
_SEPARATOR = " · "
_MISSING = "—"  # em-dash placeholder for missing fields
_DIVIDER = "———"  # triple em-dash divider between header and events

# Slack emoji shortcodes — render the same as the literal unicode glyphs and
# stay readable in source.
_EMOJI_SUCCESS = ":white_check_mark:"
_EMOJI_FAILURE = ":x:"


def _is_success(status: str | None) -> bool:
    if not status:
        return False
    return status.upper() in _SUCCESS_STATUSES


def _humanize_timestamp(iso: str | None) -> str:
    """Render an ISO timestamp as `2026 May 11 11:38:31 AM` (POSIX `%-d`).

    Falls back to the missing placeholder on falsy / unparseable input so a
    partial row still renders without raising.
    """
    if not iso:
        return _MISSING
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return _MISSING
    return dt.strftime("%Y %b %-d %I:%M:%S %p")


def _format_file_count(event: dict[str, Any]) -> str:
    """Render the file-count summary; empty string when no totals available."""
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
    """Format one event as a single Slack mrkdwn line.

    Fields are middle-dot separated; the file-count column is omitted when
    `additional_data` is empty so the line collapses to 5 fields, not 6.
    """
    parts = [
        event.get("timestamp") or _MISSING,
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
    """Project a buffered payload into the canonical per-event dict.

    Unified shape across Slack/API and IMMEDIATE/BATCHED. `pipeline_id` is
    intentionally dropped here — neither channel surfaces it. Timestamps are
    humanized once at projection so Slack and API consumers see the same
    string (implicit UTC, no timezone suffix).
    """
    event: dict[str, Any] = {
        "type": payload.get("type") or "",
        "pipeline_name": payload.get("pipeline_name") or "",
        "status": payload.get("status") or "",
        "execution_id": payload.get("execution_id") or "",
        "timestamp": _humanize_timestamp(payload.get("timestamp")),
        "additional_data": payload.get("additional_data") or {},
    }
    error_message = payload.get("error_message")
    if error_message:
        event["error_message"] = error_message
    return event


def build_envelope(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the canonical envelope used by every dispatch path.

    Summary carries only `{total, succeeded, failed}` — same shape for
    IMMEDIATE and BATCHED so receivers parse one envelope, not two.
    """
    capped = payloads[:MAX_BATCH_SIZE]
    succeeded = sum(1 for p in capped if _is_success(p.get("status")))
    failed = len(capped) - succeeded
    return {
        "summary": {
            "total": len(capped),
            "succeeded": succeeded,
            "failed": failed,
        },
        "events": [_event_from_payload(p) for p in capped],
    }


def render_for_slack(envelope: dict[str, Any]) -> dict[str, Any]:
    """Render the envelope as `{"text": "<mrkdwn>"}` for Slack.

    Header + divider are emitted for every dispatch — IMMEDIATE, BATCHED N=1,
    and BATCHED N>1 all share the same shape. Visible events are capped at
    SLACK_MAX_DISPLAY_EVENTS with an `_… and K more_` overflow footer.
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
    return {"text": "\n".join(sections)}


def render_clubbed_message(
    payloads: list[dict[str, Any]],
    platform: str,
) -> dict[str, Any]:
    """Top-level entry — returns the dispatch body for `platform`.

    Used by every dispatch site (BATCHED flush, IMMEDIATE backend providers)
    so the receiver-visible payload is identical regardless of mode.
    """
    envelope = build_envelope(payloads)
    if platform == PlatformType.SLACK.value:
        return render_for_slack(envelope)
    if platform == PlatformType.API.value:
        return envelope
    # Unknown platform — fall back to the raw envelope and warn so misrouted
    # rows don't drop silently.
    logger.warning(
        "Unknown platform %s for clubbed dispatch; returning raw envelope",
        platform,
    )
    return envelope
