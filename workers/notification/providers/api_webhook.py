"""API Webhook Notification Provider

Wraps single-event payloads (flat per-event dict) in the canonical envelope so
API webhook receivers always see the same ``{"summary": {...}, "events": [...]}``
shape. The decision is purely shape-based: a payload already in envelope shape
(it contains ``events`` — e.g. a backend buffer-rendered batch) passes through
unchanged; only a flat per-event dict is wrapped here.
"""

from typing import Any

from notification.providers.webhook_provider import WebhookProvider
from shared.infrastructure.logging import WorkerLogger
from unstract.core.notification_clubbed_renderer import build_envelope

logger = WorkerLogger.get_logger(__name__)


class APIWebhook(WebhookProvider):
    """Standard API webhook provider.

    Normalises the payload to the canonical envelope before POSTing so
    programmatic consumers parse one schema regardless of how the
    notification was produced.
    """

    def __init__(self) -> None:
        """Initialize API webhook provider."""
        super().__init__()
        self.provider_name = "APIWebhook"

    def prepare_data(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Prepare API webhook data.

        Wraps a flat per-event payload in the canonical envelope; payloads
        already in envelope shape (backend buffer-rendered) pass through.
        """
        prepared_data = super().prepare_data(notification_data)

        if "payload" in prepared_data:
            payload = prepared_data["payload"]
            if isinstance(payload, dict) and "events" not in payload:
                prepared_data["payload"] = build_envelope(payloads=[payload])

        logger.debug(f"Prepared API webhook data for {notification_data.get('url')}")
        return prepared_data
