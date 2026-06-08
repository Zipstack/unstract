"""Slack Webhook Notification Provider

Renders single-event payloads (flat per-event dict) into the same single-line
Slack body the backend produces via ``clubbed_renderer``. The decision is
purely shape-based: a payload already rendered to ``{"text": "<mrkdwn>"}``
(e.g. a backend buffer-rendered batch) passes through unchanged; only a flat
per-event dict is wrapped and rendered here.
"""

from typing import Any

from notification.providers.webhook_provider import WebhookProvider
from shared.infrastructure.logging import WorkerLogger

from unstract.core.notification_clubbed_renderer import (
    build_envelope,
    render_slack_text,
)

logger = WorkerLogger.get_logger(__name__)


class SlackWebhook(WebhookProvider):
    """Slack-specific webhook provider.

    Renders flat single-event payloads via the worker-side mirror of the
    backend clubbed renderer, then sends them as Slack-native ``text``
    mrkdwn.
    """

    def __init__(self) -> None:
        """Initialize Slack webhook provider."""
        super().__init__()
        self.provider_name = "SlackWebhook"

    def prepare_data(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Prepare Slack-specific webhook data.

        Args:
            notification_data: Raw notification data

        Returns:
            Prepared notification data with Slack formatting
        """
        prepared_data = super().prepare_data(notification_data)

        if "payload" in prepared_data:
            prepared_data["payload"] = self.format_payload(prepared_data["payload"])

        return prepared_data

    def format_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Format the payload to match Slack's expected structure.

        Two input shapes are accepted:
        - Backend-rendered ``{"text": "<mrkdwn>"}`` (any backend dispatch
          through ``clubbed_renderer``) — passed through.
        - Flat per-event dict from the generic internal webhook-send endpoints —
          wrapped in a single-event envelope and rendered to the canonical
          single-line mrkdwn body.
        """
        if "text" in payload and "events" not in payload:
            return {"text": payload["text"]}

        envelope = build_envelope(payloads=[payload])
        return {"text": render_slack_text(envelope)}

    def get_destination(self, notification_data: dict[str, Any]) -> str:
        """Extract webhook URL from notification data with masking for security."""
        url = notification_data.get("url", "unknown")

        # Mask sensitive webhook URLs for logging security
        if isinstance(url, str) and url != "unknown":
            if "hooks.slack.com" in url:
                # Mask Slack webhook tokens
                parts = url.split("/")
                if len(parts) >= 3:
                    return (
                        f"hooks.slack.com/services/{parts[-3][:4]}.../{parts[-2][:4]}..."
                    )
            elif len(url) > 50:
                # Mask long URLs that might contain tokens
                return url[:30] + "..." + url[-10:]

        return str(url)
