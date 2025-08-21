"""Shared utilities for webhook notifications.

Common functions used by both Pipeline and API notification systems.
"""

import logging
from typing import Any

from notification_v2.enums import AuthorizationType

logger = logging.getLogger(__name__)


def get_webhook_headers(notification) -> dict[str, str]:
    """Get headers for webhook notification.

    Shared logic for generating webhook headers based on notification
    authorization configuration. Used by both Pipeline and API notifications.

    Args:
        notification: Notification object with authorization fields

    Returns:
        Dict[str, str]: Headers dictionary for webhook request
    """
    headers = {"Content-Type": "application/json"}

    try:
        auth_type = AuthorizationType(notification.authorization_type.upper())
        auth_key = notification.authorization_key
        auth_header = notification.authorization_header

        if auth_type == AuthorizationType.BEARER and auth_key:
            headers["Authorization"] = f"Bearer {auth_key}"
        elif auth_type == AuthorizationType.API_KEY and auth_key:
            headers["Authorization"] = auth_key
        elif auth_type == AuthorizationType.CUSTOM_HEADER and auth_header and auth_key:
            headers[auth_header] = auth_key
        # NONE type just uses Content-Type header

    except ValueError as e:
        logger.warning(
            f"Invalid authorization type for notification {notification.id}: {e}"
        )
        # Use default headers if auth type is invalid

    return headers


def send_webhook_to_worker(
    notification, payload: dict[str, Any], queue: str = "notifications"
) -> None:
    """Send webhook notification to worker queue.

    Shared function for sending webhook notifications to the notification worker.
    Used by both Pipeline and API notification systems.

    Args:
        notification: Notification object with webhook configuration
        payload: Notification payload data
        queue: Celery queue name (default: "notifications")
    """
    from backend.celery_service import app as celery_app

    if notification.notification_type == "WEBHOOK":
        celery_app.send_task(
            "send_webhook_notification",
            args=[
                notification.url,
                payload,
                get_webhook_headers(notification),
                10,  # timeout
            ],
            kwargs={
                "max_retries": notification.max_retries,
                "retry_delay": 10,
            },
            queue=queue,
        )
        logger.info(f"Sent webhook notification to worker queue for {notification.url}")
