# notifications.py

import logging
from typing import Any, Optional

import requests
from celery import shared_task
from notification.enums import AuthorizationType
from notification.provider.notification_provider import NotificationProvider

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
        send_webhook_notification.apply_async(
            (self.notification.url, self.payload, headers, self.NOTIFICATION_TIMEOUT),
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
        """
        Get the headers for the notification based on the authorization type and key.
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
                raise ValueError(
                    "Custom header or key missing for custom authorization."
                )
        return headers


@shared_task(bind=True, name="send_webhook_notification")
def send_webhook_notification(
    self,
    url: str,
    payload: Any,
    headers: Any = None,
    timeout: int = 10,
    max_retries: Optional[int] = None,
    retry_delay: int = 10,
):
    """Celery task to send a webhook with retries and error handling.

    Args:
        url (str): The URL to which the webhook should be sent.
        payload (dict): The payload to be sent in the webhook request.
        headers (dict, optional): Optional headers to include in the request.
        Defaults to None.
        timeout (int, optional): The request timeout in seconds. Defaults to 10.
        max_retries (int, optional): The maximum number of retries allowed.
        Defaults to None.
        retry_delay (int, optional): The delay between retries in seconds.
        Defaults to 10.

    Returns:
        None
    """
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        if not (200 <= response.status_code < 300):
            logger.error(
                f"Request to {url} failed with status code {response.status_code}. "
                f"Response: {response.text}"
            )
    except requests.exceptions.RequestException as exc:
        if max_retries is not None:
            if self.request.retries < max_retries:
                logger.warning(
                    f"Request to {url} failed. Retrying in {retry_delay} seconds. "
                    f"Attempt {self.request.retries + 1}/{max_retries}. Error: {exc}"
                )
                raise self.retry(exc=exc, countdown=retry_delay)
            else:
                logger.error(
                    f"Failed to send webhook to {url} after {max_retries} attempts. "
                    f"Error: {exc}"
                )
                return None
        else:
            logger.error(f"Webhook request to {url} failed with error: {exc}")
            return None
