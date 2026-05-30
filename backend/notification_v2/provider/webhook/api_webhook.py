from typing import Any

from notification_v2.clubbed_renderer import build_envelope
from notification_v2.provider.webhook.webhook import Webhook


class APIWebhook(Webhook):
    def send(self) -> None:
        """Send the API webhook notification.

        Wraps the single event in the canonical envelope before queueing so the
        receiver-visible JSON shape matches the clubbed dispatch —
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
        """Wrap a single event in the canonical envelope.

        Receivers parse the same `{summary, events}` shape whether the event
        was sent on its own or as part of a clubbed batch.
        """
        return build_envelope(payloads=[self.payload])
