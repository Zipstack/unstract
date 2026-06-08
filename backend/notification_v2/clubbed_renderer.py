"""Backend dispatch entry for clubbed-notification rendering.

Delegates the canonical envelope + Slack body to
``unstract.core.notification_clubbed_renderer`` so backend and worker
callbacks emit byte-identical receiver-visible payloads. This thin shim
keeps the ``render_clubbed_message`` platform dispatcher (uses
``PlatformType`` enum) backend-side; everything else lives in the shared
module.
"""

from __future__ import annotations

import logging
from typing import Any

from notification_v2.enums import PlatformType
from unstract.core.notification_clubbed_renderer import (
    MAX_BATCH_SIZE,
    build_envelope,
    render_slack_text,
)

logger = logging.getLogger(__name__)

# build_envelope is imported for internal use below; it is intentionally not
# re-exported — callers import it straight from unstract.core.
__all__ = ["MAX_BATCH_SIZE", "render_clubbed_message"]


def _render_for_slack(envelope: dict[str, Any]) -> dict[str, Any]:
    """Wrap the rendered Slack mrkdwn body in the dict shape Slack expects."""
    return {"text": render_slack_text(envelope)}


def render_clubbed_message(
    payloads: list[dict[str, Any]],
    platform: str,
) -> dict[str, Any]:
    """Top-level entry — returns the dispatch body for ``platform``.

    Used by every dispatch site so the receiver-visible payload is
    identical regardless of caller.
    """
    envelope = build_envelope(payloads)
    if platform == PlatformType.SLACK.value:
        return _render_for_slack(envelope)
    if platform == PlatformType.API.value:
        return envelope
    # Unknown platform — fall back to the raw envelope and warn so misrouted
    # rows don't drop silently.
    logger.warning(
        "Unknown platform %s for clubbed dispatch; returning raw envelope",
        platform,
    )
    return envelope
