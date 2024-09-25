import logging
from typing import Any

from notification_v2.enums import NotificationType, PlatformType
from notification_v2.models import Notification
from notification_v2.provider.notification_provider import NotificationProvider
from notification_v2.provider.registry import get_notification_provider

logger = logging.getLogger(__name__)


class NotificationHelper:
    @classmethod
    def send_notification(cls, notifications: list[Notification], payload: Any) -> None:
        """Send notification Sends notifications using the appropriate provider
        based on the notification type and platform.

        This method iterates through a list of `Notification` objects, determines the
        appropriate notification provider based on the notification's type and
        platform, and sends the notification with the provided payload. If an error
        occurs due to an invalid notification type or platform, it logs the error.

        Args:
            notifications (list[Notification]): A list of `Notification` instances to
                be processed and sent.
            payload (Any): The data to be sent with the notification. This can be any
                format expected by the provider

            Returns:
                None
        """
        for notification in notifications:
            notification_type = NotificationType(notification.notification_type)
            platform_type = PlatformType(notification.platform)
            try:
                notification_provider = get_notification_provider(
                    notification_type, platform_type
                )
                notifier: NotificationProvider = notification_provider(
                    notification=notification, payload=payload
                )
                notifier.send()
                logger.info(f"Sending notification to {notification}")
            except ValueError as e:
                logger.error(
                    f"Error in notification type {notification_type} and platform "
                    f"{platform_type} for notification {notification}: {e}"
                )
