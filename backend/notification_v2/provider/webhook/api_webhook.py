from typing import Any

from notification_v2.clubbed_renderer import build_envelope
from notification_v2.provider.webhook.webhook import Webhook


class APIWebhook(Webhook):
    def send(self) -> None:
        """Send the API webhook notification.

        Wraps the IMMEDIATE event in the canonical envelope before queueing
        so the receiver-visible JSON shape matches BATCHED dispatches —
        `{"summary": {...}, "events": [{...}]}`.
        """
        self.payload = self.format_payload()
        super().send()

    def get_headers(self) -> dict[str, str]:
        """API-specific headers."""
        headers = super().get_headers()
        headers["Content-Type"] = "application/json"
        return headers

    def format_payload(self) -> dict[str, Any]:
        """Wrap a single IMMEDIATE event in the canonical envelope.

        `interval_seconds=None` -> `summary.interval_minutes` is null;
        receivers can use that to distinguish IMMEDIATE from BATCHED.
        """
        return build_envelope(payloads=[self.payload], interval_seconds=None)
