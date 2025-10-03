"""API Webhook Notification Provider

Standard API webhook provider for generic webhook endpoints.
"""

from typing import Any

from notification.providers.webhook_provider import WebhookProvider
from shared.infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class APIWebhook(WebhookProvider):
    """Standard API webhook provider.

    Handles generic webhook notifications without platform-specific formatting.
    Sends the payload as-is in JSON format.
    """

    def __init__(self):
        """Initialize API webhook provider."""
        super().__init__()
        self.provider_name = "APIWebhook"

    def prepare_data(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Prepare API webhook data.

        For standard API webhooks, we send the payload as-is without
        any special formatting.

        Args:
            notification_data: Raw notification data

        Returns:
            Prepared notification data
        """
        logger.debug(
            f"Preparing standard API webhook data for {notification_data.get('url')}"
        )
        return super().prepare_data(notification_data)
