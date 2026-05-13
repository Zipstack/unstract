from notification_v2.enums import NotificationType, PlatformType
from notification_v2.provider.notification_provider import NotificationProvider
from notification_v2.provider.webhook.api_webhook import APIWebhook
from notification_v2.provider.webhook.slack_webhook import SlackWebhook

REGISTRY = {
    NotificationType.WEBHOOK: {
        PlatformType.SLACK: SlackWebhook,
        PlatformType.API: APIWebhook,
        # Add other platform-specific classes here
    },
    # Add other notification types and classes here
}


def get_notification_provider(
    notification_type: NotificationType, platform_type: PlatformType
) -> NotificationProvider:
    """Get Notification provider based on notification type and platform type
    It uses the REGISTRY to map the combination of notification type and
    platform type to the corresponding NotificationProvider class.

    If the provided combination is not found in the REGISTRY, a ValueError is raised.

    Note:
        This function assumes that the REGISTRY dictionary is correctly populated
        with the appropriate NotificationProvider classes for each combination of
        notification type and platform type.

    See Also:
        - NotificationType
        - PlatformType
        - NotificationProvider
        - REGISTRY

    Parameters:
        notification_type (NotificationType): The type of notification.
        platform_type (PlatformType): The platform/provider type for the notification.

    Returns:
        NotificationProvider: The appropriate NotificationProvider class for
        the given combination.

    Raises:
        ValueError: If the provided combination is not found in the REGISTRY.
    """
    if notification_type not in REGISTRY:
        raise ValueError(f"Unsupported notification type: {notification_type}")

    platform_registry = REGISTRY[notification_type]
    if platform_type not in platform_registry:
        raise ValueError(f"Unsupported platform type: {platform_type}")

    return platform_registry[platform_type]
