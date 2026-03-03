import logging

from backend.celery_service import app as celery_app
from notification_v2.enums import AuthorizationType
from notification_v2.provider.notification_provider import NotificationProvider

logger = logging.getLogger(__name__)


class WebhookNotificationArg:
    MAX_RETRIES = "max_retries"
    RETRY_DELAY = "retry_delay"


class HeaderConstants:
    APPLICATION_JSON = "application/json"


class Webhook(NotificationProvider):
    def send(self):
        """Send the webhook notification."""
        try:
            headers = self.get_headers()
            self.validate()
        except ValueError as e:
            logger.error(f"Error validating notification {self.notification} :: {e}")
            return
        celery_app.send_task(
            "send_webhook_notification",
            args=[
                self.notification.url,
                self.payload,
                headers,
                self.NOTIFICATION_TIMEOUT,
            ],
            kwargs={
                WebhookNotificationArg.MAX_RETRIES: self.notification.max_retries,
                WebhookNotificationArg.RETRY_DELAY: self.RETRY_DELAY,
            },
        )

    def validate(self):
        """Validate notification.

        Returns:
            _type_: None
        """
        if not self.notification.url:
            raise ValueError("Webhook URL is required.")
        if not self.payload:
            raise ValueError("Payload is required.")
        return super().validate()

    def get_headers(self):
        """Get the headers for the notification based on the authorization type and key.

        Raises:
            ValueError: _description_

        Returns:
            dict[str, str]: A dictionary containing the headers.
        """
        headers = {}
        try:
            authorization_type = AuthorizationType(
                self.notification.authorization_type.upper()
            )
        except ValueError:
            raise ValueError(
                "Unsupported authorization type: "
                f"{self.notification.authorization_type}"
            )
        authorization_key = self.notification.authorization_key
        authorization_header = self.notification.authorization_header

        header_formats = {
            AuthorizationType.BEARER: lambda key: {
                "Authorization": f"Bearer {key}",
                "Content-Type": HeaderConstants.APPLICATION_JSON,
            },
            AuthorizationType.API_KEY: lambda key: {
                "Authorization": key,
                "Content-Type": HeaderConstants.APPLICATION_JSON,
            },
            AuthorizationType.CUSTOM_HEADER: lambda key: {
                authorization_header: key,
                "Content-Type": HeaderConstants.APPLICATION_JSON,
            },
            AuthorizationType.NONE: lambda _: {
                "Content-Type": HeaderConstants.APPLICATION_JSON,
            },
        }

        if authorization_type not in header_formats:
            raise ValueError(f"Unsupported authorization type: {authorization_type}")

        headers = header_formats[authorization_type](authorization_key)

        # Check if custom header type has required details
        if authorization_type == AuthorizationType.CUSTOM_HEADER:
            if not authorization_header or not authorization_key:
                raise ValueError("Custom header or key missing for custom authorization.")
        return headers
