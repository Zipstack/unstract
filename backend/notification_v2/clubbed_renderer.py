"""Clubbed notification renderer.

Builds one canonical JSON envelope from a group of buffered execution events
and emits the platform-appropriate dispatch payload. Stays separate from the
single-event SlackWebhook / APIWebhook providers so immediate-dispatch behavior
stays untouched.

Envelope shape (always the same — single-event groups use this too so consumers
never need to branch on "is this batched?"):

    {
        "kind": "batch",
        "summary": {
            "pipeline": "<name>",
            "interval_minutes": 30,
            "total": N, "succeeded": S, "failed": F
        },
        "events": [{"execution_id": ..., "status": ..., "error": ...?}, ...]
    }
"""

from __future__ import annotations

import logging
from typing import Any

from notification_v2.enums import PlatformType

logger = logging.getLogger(__name__)

# Hard cap on events per dispatch — extras roll over to the next flush tick.
# Bounds memory + payload size and prevents a runaway backlog from creating an
# unbounded HTTP body.
MAX_BATCH_SIZE = 500
# How many events Slack renders inline before collapsing the rest under a
# "… and K more" footer. Slack tolerates much larger payloads, but readability
# tanks past ~25 lines.
SLACK_MAX_DISPLAY_EVENTS = 25

_SUCCESS_STATUSES = {"COMPLETED", "SUCCESS"}


def _is_success(status: str | None) -> bool:
    if not status:
        return False
    return status.upper() in _SUCCESS_STATUSES


def _event_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {
        "execution_id": payload.get("execution_id"),
        "status": payload.get("status"),
    }
    error_message = payload.get("error_message")
    if error_message:
        event["error"] = error_message
    return event


def build_envelope(
    payloads: list[dict[str, Any]], interval_seconds: int
) -> dict[str, Any]:
    """Build the canonical batch envelope.

    Caps the events list at MAX_BATCH_SIZE; oldest-first ordering is the
    caller's responsibility (the flush job sorts by created_at).
    """
    capped = payloads[:MAX_BATCH_SIZE]
    succeeded = sum(1 for p in capped if _is_success(p.get("status")))
    failed = len(capped) - succeeded
    # Multiple pipelines can share an (org, url, auth_sig) group; we surface
    # the first one's name as a representative. Mixed-pipeline batches are
    # rare in practice and a v2 enhancement would aggregate distinct names.
    pipeline_name = capped[0].get("pipeline_name") if capped else None
    return {
        "kind": "batch",
        "summary": {
            "pipeline": pipeline_name,
            "interval_minutes": max(1, interval_seconds // 60),
            "total": len(capped),
            "succeeded": succeeded,
            "failed": failed,
        },
        "events": [_event_from_payload(p) for p in capped],
    }


def _slack_event_line(event: dict[str, Any]) -> str:
    parts = [f"— {event.get('execution_id') or 'unknown'}: {event.get('status')}"]
    if event.get("error"):
        parts.append(f"({event['error']})")
    return " ".join(parts)


def render_for_slack(envelope: dict[str, Any]) -> dict[str, Any]:
    """Format the envelope as a Slack-compatible payload dict.

    Returns the body shape Slack incoming webhooks expect (`text` field with
    mrkdwn). Truncates inline events at SLACK_MAX_DISPLAY_EVENTS.
    """
    summary = envelope["summary"]
    events: list[dict[str, Any]] = envelope["events"]
    pipeline = summary.get("pipeline") or "pipeline"

    header = f"*[Unstract] {summary['total']} executions for `{pipeline}`*"
    counts = f"✅ {summary['succeeded']} succeeded  ❌ {summary['failed']} failed"

    visible = events[:SLACK_MAX_DISPLAY_EVENTS]
    lines = [_slack_event_line(e) for e in visible]
    overflow = len(events) - len(visible)
    if overflow > 0:
        lines.append(f"… and {overflow} more executions")

    body = "\n".join([header, counts, *lines])
    return {"text": body}


def render_clubbed_message(
    payloads: list[dict[str, Any]], platform: str, interval_seconds: int
) -> dict[str, Any]:
    """Top-level entry point — returns the dispatch body for ``platform``.

    Slack receives the rendered text payload; raw API webhooks receive the
    canonical envelope unchanged so downstream consumers can parse it
    programmatically.
    """
    envelope = build_envelope(payloads, interval_seconds)
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
