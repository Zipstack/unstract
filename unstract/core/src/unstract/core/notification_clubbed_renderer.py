"""Shared clubbed-notification envelope + Slack renderer.

Imported by both `backend/notification_v2/clubbed_renderer.py` and the
worker `notification/providers/*_webhook.py` so the receiver-visible
payload (envelope JSON for API, mrkdwn string for Slack) is byte-identical
regardless of which side rendered it.

Envelope shape:

    {
        "summary": {"total": N, "succeeded": S, "failed": F},
        "events": [
            {
                "type": "ETL" | "TASK" | "API",
                "pipeline_name": "...",
                "status": "ERROR" | "SUCCESS" | ...,
                "is_failure": bool,   # optional; authoritative verdict the
                                      # renderer prefers over status+counts
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

`pipeline_id` is intentionally absent — neither channel surfaces it.
"""

from __future__ import annotations

import datetime
from typing import Any

from unstract.core.data_models import is_failure_run

# Hard cap on events per dispatch; the rest roll into the next flush tick.
MAX_BATCH_SIZE = 500
# Slack inlines this many events before collapsing the rest under an
# "_… and K more_" footer. Slack tolerates much larger payloads, but
# readability tanks past ~25 lines.
SLACK_MAX_DISPLAY_EVENTS = 25

# Legacy single-run webhook keys (pre-clubbing flat shape). Spread onto a
# single-event envelope for backward compatibility — see build_envelope.
# Covers both pre-clubbing wire shapes: the backend dispatch DTO
# (pipeline_v2.dto.PipelineStatusPayload.to_dict — the first six keys) and the
# worker callback path (core.data_models.NotificationPayload.to_webhook_payload),
# which additionally emitted top-level ``timestamp`` and ``additional_data``.
_LEGACY_FLAT_KEYS = (
    "type",
    "pipeline_id",
    "pipeline_name",
    "status",
    "execution_id",
    "error_message",
    "timestamp",
    "additional_data",
)

# Middle dot (U+00B7) padded by single spaces — the per-event field separator.
_SEPARATOR = " · "
_MISSING = "—"  # em-dash placeholder for missing fields
_DIVIDER = "———"  # triple em-dash divider between header and events

# Slack emoji shortcodes — render the same as the literal unicode glyphs and
# stay readable in source.
_EMOJI_SUCCESS = ":white_check_mark:"
_EMOJI_FAILURE = ":x:"


def _is_effective_failure(event: dict[str, Any]) -> bool:
    """Did this event fail? Single-sourced with the dispatch filter.

    Prefers the authoritative ``is_failure`` verdict the dispatch site computed
    and carried on the payload, so classification does not depend on the
    ``status`` string — whose vocabulary differs per dispatch path
    (``PipelineStatus`` on the backend pipeline path vs ``ExecutionStatus``
    elsewhere) and which core ``is_failure_run`` only understands as
    ``ExecutionStatus``. Falls back to ``is_failure_run(status, failed_files)``
    when the flag is absent (worker / legacy flat payloads), so the rendered
    outcome can never disagree with the reason the alert fired.
    """
    explicit = event.get("is_failure")
    if explicit is not None:
        return bool(explicit)
    counts = event.get("additional_data") or {}
    return is_failure_run(event.get("status"), counts.get("failed_files"))


def _humanize_timestamp(iso: str | None) -> str:
    """Render an ISO timestamp as `2026 May 11 11:38:31 AM`.

    Falls back to the missing placeholder on falsy / unparseable input so a
    partial row still renders without raising. The day is interpolated from
    ``dt.day`` rather than a ``%-d`` directive: ``%-d`` is a glibc extension
    that raises ``ValueError`` on macOS/Windows, and this call sits in the
    flush render path where an unhandled raise drops the whole batch.
    """
    if not iso:
        return _MISSING
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return _MISSING
    return f"{dt.strftime('%Y %b')} {dt.day} {dt.strftime('%I:%M:%S %p')}"


def _format_file_count(event: dict[str, Any]) -> str:
    """Render the file-count summary; empty string when no totals available.

    A COMPLETED run with file failures short-circuits to the failure shape so
    the rendered line matches why a failures-only notification fired.
    """
    counts = event.get("additional_data") or {}
    total = counts.get("total_files")
    if total is None:
        return ""
    if _is_effective_failure(event):
        failed = counts.get("failed_files", 0)
        return f"{_EMOJI_FAILURE} {failed}/{total} files"
    successful = counts.get("successful_files", 0)
    return f"{_EMOJI_SUCCESS} {successful}/{total} files"


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

    Unified shape across Slack/API and every dispatch path. `pipeline_id`
    is intentionally dropped — neither channel surfaces it. Timestamps are
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
    # Authoritative failure verdict from the dispatch site; carried only when
    # set so worker / legacy event dicts (which fall back to status+counts)
    # stay byte-identical.
    is_failure = payload.get("is_failure")
    if is_failure is not None:
        event["is_failure"] = is_failure
    return event


def build_envelope(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the canonical envelope used by every dispatch path.

    Summary carries `{total, succeeded, failed}`; `events` is the per-run list.

    Backward compatibility: when the batch holds exactly one event, the legacy
    flat top-level fields (the pre-clubbing single-run shape) are also spread
    onto the envelope alongside `summary`/`events`. This reproduces both legacy
    wire shapes — the backend DTO (`type, pipeline_id, pipeline_name, status,
    execution_id?, error_message?`) and the worker callback body, which also
    carried top-level `timestamp` and `additional_data`. Receivers written
    against either old body keep working; new receivers read `events`.
    Multi-event batches are envelope-only (there was never a flat shape for
    them). Removable once all receivers have migrated to `events`.
    """
    capped = payloads[:MAX_BATCH_SIZE]
    failed = sum(1 for p in capped if _is_effective_failure(p))
    envelope: dict[str, Any] = {
        "summary": {
            "total": len(capped),
            "succeeded": len(capped) - failed,
            "failed": failed,
        },
        "events": [_event_from_payload(p) for p in capped],
    }
    if len(capped) == 1:
        single = capped[0]
        for key in _LEGACY_FLAT_KEYS:
            if single.get(key) is not None:
                envelope[key] = single[key]
    return envelope


def render_slack_text(envelope: dict[str, Any]) -> str:
    """Render the envelope as Slack mrkdwn body text.

    Header + divider are emitted for every dispatch — single-event and
    multi-event batches share the same shape. Visible events are capped at
    ``SLACK_MAX_DISPLAY_EVENTS`` with an `_… and K more_` overflow footer.
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
