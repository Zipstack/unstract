from enum import Enum


class NotificationType(Enum):
    WEBHOOK = "WEBHOOK"
    # Add other notification types as needed
    # Example EMAIL = 'EMAIL'

    def get_valid_platforms(self):
        if self == NotificationType.WEBHOOK:
            return [PlatformType.SLACK.value, PlatformType.API.value]
        return []

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class AuthorizationType(Enum):
    BEARER = "BEARER"
    API_KEY = "API_KEY"
    CUSTOM_HEADER = "CUSTOM_HEADER"
    NONE = "NONE"

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class PlatformType(Enum):
    SLACK = "SLACK"
    API = "API"
    # Add other platforms as needed
    # Example TEAMS = 'TEAMS'

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class DeliveryMode(Enum):
    """Per-notification dispatch mode.

    IMMEDIATE fires on every workflow completion (pre-existing behavior).
    BATCHED buffers events into NotificationBuffer and flushes them as one
    clubbed message per (org, webhook_url, auth_sig) every
    NOTIFICATION_CLUB_INTERVAL seconds.
    """

    IMMEDIATE = "IMMEDIATE"
    BATCHED = "BATCHED"

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]


class BufferStatus(Enum):
    """Lifecycle states for a NotificationBuffer row.

    PENDING       — waiting for the next flush tick.
    DISPATCHED    — successfully sent as part of a clubbed message.
    DEAD_LETTER   — Celery exhausted retries; terminal, never re-picked.
    """

    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    DEAD_LETTER = "DEAD_LETTER"

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]
