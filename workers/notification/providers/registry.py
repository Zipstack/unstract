"""Notification Provider Registry

Registry pattern for mapping notification types and platform types
to their appropriate provider implementations.
"""

from notification.enums import PlatformType
from notification.providers.api_webhook import APIWebhook
from notification.providers.base_provider import BaseNotificationProvider
from notification.providers.slack_webhook import SlackWebhook
from shared.infrastructure.logging import WorkerLogger

from unstract.core.notification_enums import NotificationType

logger = WorkerLogger.get_logger(__name__)

# Provider registry mapping notification type and platform to provider class
PROVIDER_REGISTRY = {
    NotificationType.WEBHOOK: {
        PlatformType.SLACK: SlackWebhook,
        PlatformType.API: APIWebhook,
        # Add other webhook platforms here
        # PlatformType.TEAMS: TeamsWebhook,
        # PlatformType.DISCORD: DiscordWebhook,
    },
    # Add other notification types here
    # NotificationType.EMAIL: {
    #     PlatformType.SMTP: SMTPProvider,
    #     PlatformType.SENDGRID: SendGridProvider,
    # },
    # NotificationType.SMS: {
    #     PlatformType.TWILIO: TwilioProvider,
    #     PlatformType.AWS_SNS: SNSProvider,
    # },
}


def get_notification_provider(
    notification_type: NotificationType, platform_type: PlatformType
) -> type[BaseNotificationProvider]:
    """Get notification provider class based on type and platform.

    Args:
        notification_type: Type of notification (WEBHOOK, EMAIL, etc.)
        platform_type: Platform/provider type (SLACK, API, etc.)

    Returns:
        Provider class for the given combination

    Raises:
        ValueError: If the combination is not supported
    """
    logger.debug(f"Looking up provider for {notification_type} + {platform_type}")

    if notification_type not in PROVIDER_REGISTRY:
        raise ValueError(f"Unsupported notification type: {notification_type}")

    platform_registry = PROVIDER_REGISTRY[notification_type]
    if platform_type not in platform_registry:
        raise ValueError(
            f"Unsupported platform type '{platform_type}' for notification type '{notification_type}'"
        )

    provider_class = platform_registry[platform_type]
    logger.debug(f"Found provider: {provider_class.__name__}")
    return provider_class


def create_notification_provider(
    notification_type: NotificationType, platform_type: PlatformType
) -> BaseNotificationProvider:
    """Create and instantiate a notification provider.

    Args:
        notification_type: Type of notification
        platform_type: Platform/provider type

    Returns:
        Instantiated provider ready for use

    Raises:
        ValueError: If the combination is not supported
    """
    provider_class = get_notification_provider(notification_type, platform_type)
    return provider_class()


def create_provider_from_config(notification_config: dict) -> BaseNotificationProvider:
    """Create provider instance from notification configuration.

    Args:
        notification_config: Notification config from backend API containing
                           'notification_type' and 'platform' fields

    Returns:
        Instantiated provider ready for use

    Raises:
        ValueError: If the configuration is invalid or unsupported
    """
    notification_type = NotificationType(
        notification_config.get("notification_type", "WEBHOOK")
    )
    platform_str = notification_config.get("platform")

    if not platform_str:
        # Default to API platform for backward compatibility
        platform_type = PlatformType.API
        logger.warning(f"No platform specified in config, defaulting to {platform_type}")
    else:
        platform_type = PlatformType(platform_str)

    logger.debug(f"Creating provider for {notification_type} + {platform_type}")
    return create_notification_provider(notification_type, platform_type)


def list_supported_combinations() -> dict[str, list[str]]:
    """List all supported notification type and platform combinations."""
    combinations = {}
    for notification_type, platforms in PROVIDER_REGISTRY.items():
        combinations[notification_type.value] = [
            platform.value for platform in platforms.keys()
        ]
    return combinations


def is_combination_supported(
    notification_type: NotificationType, platform_type: PlatformType
) -> bool:
    """Check if a notification type and platform combination is supported."""
    try:
        get_notification_provider(notification_type, platform_type)
        return True
    except ValueError:
        return False
