from enum import Enum

from workflow_manager.workflow_v2.enums import ExecutionStatus

# Single source of truth for "did this run fail for notification routing?".
# STOPPED is intentionally a failure here per migrations/0002_…notify_on_failures
# db_comment ("terminal status ERROR/STOPPED or any file in the run errored").
FAILURE_STATUSES = frozenset({ExecutionStatus.ERROR.value, ExecutionStatus.STOPPED.value})


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

    Product ships every notification as BATCHED — events buffer into
    ``NotificationBuffer`` and flush as one clubbed message per
    (org, webhook_url, auth_sig) every ``NOTIFICATION_CLUB_INTERVAL`` seconds.

    The ``IMMEDIATE`` value is purely a historical DB value — no code reads
    it anymore (the legacy synchronous-dispatch path was removed). The
    column and enum value remain so existing rows don't break; both will be
    dropped in a follow-up schema migration.
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
