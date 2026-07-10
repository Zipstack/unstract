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


class BufferStatus(Enum):
    """Lifecycle states for a NotificationBuffer row.

    PENDING       — waiting for the next flush tick.
    SENDING       — claimed by a flush and handed to the dispatch task; awaiting
                    its success/failure callback. Reclaimed to PENDING by the
                    reaper if it stays here past the dispatch lease (crash window).
    DISPATCHED    — delivery succeeded.
    DEAD_LETTER   — Celery exhausted retries, or the row hit
                    NOTIFICATION_MAX_DISPATCH_ATTEMPTS reclaim attempts; terminal,
                    never re-picked.
    """

    PENDING = "PENDING"
    SENDING = "SENDING"
    DISPATCHED = "DISPATCHED"
    DEAD_LETTER = "DEAD_LETTER"

    @classmethod
    def choices(cls):
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]
