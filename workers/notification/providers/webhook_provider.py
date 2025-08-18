"""Webhook Notification Provider

This provider handles webhook notifications with identical behavior to the current
backend implementation. It maintains full backward compatibility while providing
a foundation for future notification types.
"""

from typing import Any

import requests
from notification.providers.base_provider import (
    BaseNotificationProvider,
    DeliveryError,
    ValidationError,
)
from shared.logging_utils import WorkerLogger

from unstract.core.notification_utils import (
    build_webhook_headers,
    send_webhook_request,
    serialize_notification_data,
    validate_webhook_data,
)

logger = WorkerLogger.get_logger(__name__)


class WebhookProvider(BaseNotificationProvider):
    """Webhook notification provider.

    This provider implements webhook notifications with identical behavior to the
    current backend implementation to maintain backward compatibility.
    """

    def __init__(self):
        """Initialize webhook provider."""
        super().__init__()
        self.provider_name = "Webhook"

    def validate(self, notification_data: dict[str, Any]) -> bool:
        """Validate webhook notification data.

        Args:
            notification_data: Webhook notification data containing:
                - url: Webhook URL (required)
                - payload: JSON payload (required)
                - authorization_type: Auth type (optional)
                - authorization_key: Auth key (optional)
                - authorization_header: Custom header name (optional)

        Returns:
            True if validation passes

        Raises:
            ValidationError: If validation fails
        """
        try:
            validate_webhook_data(
                url=notification_data.get("url"),
                payload=notification_data.get("payload"),
                authorization_type=notification_data.get("authorization_type"),
                authorization_key=notification_data.get("authorization_key"),
                authorization_header=notification_data.get("authorization_header"),
            )
            return True
        except ValueError as e:
            raise ValidationError(str(e), provider=self.provider_name)

    def get_destination(self, notification_data: dict[str, Any]) -> str:
        """Extract webhook URL from notification data."""
        return notification_data.get("url", "unknown")

    def prepare_data(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Prepare webhook data for sending.

        This includes serializing UUIDs and datetimes in the payload.
        """
        prepared_data = notification_data.copy()

        # Serialize payload to handle UUIDs and datetimes
        if "payload" in prepared_data:
            prepared_data["payload"] = serialize_notification_data(
                prepared_data["payload"]
            )

        return prepared_data

    def send(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Send webhook notification.

        This method replicates the exact behavior of the current backend
        send_webhook_notification task to maintain backward compatibility.

        Args:
            notification_data: Webhook data containing:
                - url: Target webhook URL
                - payload: JSON payload to send
                - headers: Optional custom headers (defaults to auth-based headers)
                - timeout: Request timeout in seconds (default: 10)
                - max_retries: Maximum retry attempts (default: None)
                - retry_delay: Delay between retries in seconds (default: 10)
                - authorization_type: Authorization type (BEARER, API_KEY, etc.)
                - authorization_key: Authorization key/token
                - authorization_header: Custom header name (for CUSTOM_HEADER)

        Returns:
            Dictionary with send result

        Raises:
            ValidationError: If data validation fails
            DeliveryError: If delivery fails after all retries
        """
        try:
            # Validate notification data
            self.validate(notification_data)

            # Prepare data (serialize UUIDs, etc.)
            prepared_data = self.prepare_data(notification_data)

            # Extract parameters with defaults (matching backend implementation)
            url = prepared_data["url"]
            payload = prepared_data["payload"]
            timeout = prepared_data.get("timeout", 10)
            max_retries = prepared_data.get("max_retries")
            retry_delay = prepared_data.get("retry_delay", 10)

            # Build headers - either use provided headers or build from auth config
            if "headers" in prepared_data and prepared_data["headers"]:
                headers = prepared_data["headers"]
            else:
                headers = self._build_headers(prepared_data)

            logger.debug(f"Sending webhook to {url} with {len(headers)} headers")

            # Send webhook request using shared utility (identical to backend logic)
            try:
                result = send_webhook_request(
                    url=url,
                    payload=payload,
                    headers=headers,
                    timeout=timeout,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    current_retry=0,
                )

                if result.get("success"):
                    return self.format_success_result(
                        destination=url,
                        attempts=result.get("attempts", 1),
                        details={
                            "status_code": result.get("status_code"),
                            "response_text": result.get("response_text", "")[
                                :500
                            ],  # Limit response size
                        },
                    )
                else:
                    return self.format_failure_result(
                        destination=url,
                        error=Exception(result.get("error", "Unknown error")),
                        attempts=result.get("attempts", 1),
                        details=result,
                    )

            except requests.exceptions.RequestException as exc:
                # This exception will be caught by the worker retry mechanism
                # for Celery-based retry handling - identical to backend behavior
                raise DeliveryError(
                    f"Webhook request failed: {str(exc)}",
                    provider=self.provider_name,
                    destination=url,
                )

        except ValidationError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            # Wrap unexpected errors
            raise DeliveryError(
                f"Unexpected error sending webhook: {str(e)}",
                provider=self.provider_name,
                destination=notification_data.get("url", "unknown"),
            )

    def _build_headers(self, notification_data: dict[str, Any]) -> dict[str, str]:
        """Build webhook headers based on authorization configuration.

        This method uses the shared utility to maintain identical behavior
        to the backend implementation.
        """
        try:
            return build_webhook_headers(
                authorization_type=notification_data.get("authorization_type", "NONE"),
                authorization_key=notification_data.get("authorization_key"),
                authorization_header=notification_data.get("authorization_header"),
                custom_headers=notification_data.get("custom_headers"),
            )
        except ValueError as e:
            raise ValidationError(str(e), provider=self.provider_name)


# Future provider implementations can be added here:


class EmailProvider(BaseNotificationProvider):
    """Email notification provider (future implementation)."""

    def __init__(self):
        super().__init__()
        self.provider_name = "Email"

    def validate(self, notification_data: dict[str, Any]) -> bool:
        """Validate email notification data (placeholder)."""
        # TODO: Implement email validation
        raise NotImplementedError("Email notifications not yet implemented")

    def send(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Send email notification (placeholder)."""
        # TODO: Implement email sending
        raise NotImplementedError("Email notifications not yet implemented")


class SMSProvider(BaseNotificationProvider):
    """SMS notification provider (future implementation)."""

    def __init__(self):
        super().__init__()
        self.provider_name = "SMS"

    def validate(self, notification_data: dict[str, Any]) -> bool:
        """Validate SMS notification data (placeholder)."""
        # TODO: Implement SMS validation
        raise NotImplementedError("SMS notifications not yet implemented")

    def send(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Send SMS notification (placeholder)."""
        # TODO: Implement SMS sending
        raise NotImplementedError("SMS notifications not yet implemented")


class PushProvider(BaseNotificationProvider):
    """Push notification provider (future implementation)."""

    def __init__(self):
        super().__init__()
        self.provider_name = "Push"

    def validate(self, notification_data: dict[str, Any]) -> bool:
        """Validate push notification data (placeholder)."""
        # TODO: Implement push validation
        raise NotImplementedError("Push notifications not yet implemented")

    def send(self, notification_data: dict[str, Any]) -> dict[str, Any]:
        """Send push notification (placeholder)."""
        # TODO: Implement push sending
        raise NotImplementedError("Push notifications not yet implemented")
