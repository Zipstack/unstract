import logging
from typing import Any

from notification_v2.clubbed_renderer import render_clubbed_message
from notification_v2.enums import PlatformType
from notification_v2.provider.webhook.webhook import Webhook

logger = logging.getLogger(__name__)


class SlackWebhook(Webhook):
    def send(self) -> None:
        """Send the Slack webhook notification."""
        formatted_payload = self.format_payload()
        self.payload = formatted_payload
        super().send()

    def get_headers(self) -> dict[str, str]:
        """Slack-specific headers."""
        headers = super().get_headers()
        headers["Content-Type"] = "application/json"
        return headers

    def format_payload(self) -> dict[str, Any]:
        """Render the IMMEDIATE event through the canonical envelope.

        Single shared renderer for IMMEDIATE and BATCHED so receivers see the
        same Slack body shape regardless of delivery mode.
        """
        return render_clubbed_message(
            payloads=[self.payload],
            platform=PlatformType.SLACK.value,
        )
