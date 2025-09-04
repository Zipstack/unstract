"""Shared notification enums for Unstract platform.

This module contains notification-related enums that can be used by both
backend Django services and worker processes for consistent notification handling.
"""

from enum import Enum


class NotificationType(Enum):
    """Types of notifications supported by the platform."""

    WEBHOOK = "WEBHOOK"
    EMAIL = "EMAIL"  # Future implementation
    SMS = "SMS"  # Future implementation
    PUSH = "PUSH"  # Future implementation

    def get_valid_platforms(self):
        """Get valid platforms for this notification type."""
        if self == NotificationType.WEBHOOK:
            return [PlatformType.SLACK.value, PlatformType.API.value]
        elif self == NotificationType.EMAIL:
            return [PlatformType.SMTP.value, PlatformType.SENDGRID.value]
        elif self == NotificationType.SMS:
            return [PlatformType.TWILIO.value, PlatformType.AWS_SNS.value]
        elif self == NotificationType.PUSH:
            return [PlatformType.FIREBASE.value, PlatformType.APPLE_PUSH.value]
        return []

    @classmethod
    def choices(cls):
        """Get Django-compatible choices."""
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class AuthorizationType(Enum):
    """Authorization types for notifications."""

    BEARER = "BEARER"
    API_KEY = "API_KEY"
    CUSTOM_HEADER = "CUSTOM_HEADER"
    NONE = "NONE"

    @classmethod
    def choices(cls):
        """Get Django-compatible choices."""
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class PlatformType(Enum):
    """Platform types for different notification channels."""

    # Webhook platforms
    SLACK = "SLACK"
    API = "API"
    TEAMS = "TEAMS"  # Future implementation
    DISCORD = "DISCORD"  # Future implementation

    # Email platforms
    SMTP = "SMTP"  # Future implementation
    SENDGRID = "SENDGRID"  # Future implementation
    AWS_SES = "AWS_SES"  # Future implementation

    # SMS platforms
    TWILIO = "TWILIO"  # Future implementation
    AWS_SNS = "AWS_SNS"  # Future implementation

    # Push notification platforms
    FIREBASE = "FIREBASE"  # Future implementation
    APPLE_PUSH = "APPLE_PUSH"  # Future implementation

    @classmethod
    def choices(cls):
        """Get Django-compatible choices."""
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class DeliveryStatus(Enum):
    """Delivery status for notifications."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"

    @classmethod
    def choices(cls):
        """Get Django-compatible choices."""
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]

    def is_final(self) -> bool:
        """Check if this status represents a final state."""
        return self in [
            DeliveryStatus.SUCCESS,
            DeliveryStatus.FAILED,
            DeliveryStatus.CANCELLED,
        ]

    def is_active(self) -> bool:
        """Check if this status represents an active processing state."""
        return self in [
            DeliveryStatus.PENDING,
            DeliveryStatus.QUEUED,
            DeliveryStatus.SENDING,
            DeliveryStatus.RETRYING,
        ]


class NotificationPriority(Enum):
    """Priority levels for notification processing."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"

    @classmethod
    def choices(cls):
        """Get Django-compatible choices."""
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]

    def get_queue_suffix(self) -> str:
        """Get queue suffix for this priority level."""
        return f"_{self.value.lower()}" if self != NotificationPriority.NORMAL else ""
