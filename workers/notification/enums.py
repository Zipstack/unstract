"""Notification-specific enums for workers.

These enums are used to match the backend notification system exactly.
Platform detection is done in the backend and stored in the database.
"""

from enum import Enum


class PlatformType(Enum):
    """Platform types for notifications.

    Must match the backend PlatformType enum values exactly
    to ensure compatibility when fetching configs from Django.

    Platform selection is configuration-driven from the backend,
    not based on URL pattern detection.
    """

    SLACK = "SLACK"
    API = "API"
    # Add other platforms as needed (must match backend)
    # TEAMS = "TEAMS"
    # DISCORD = "DISCORD"

    @classmethod
    def choices(cls):
        """Get choices for forms/serializers."""
        return [(e.value, e.name.replace("_", " ").capitalize()) for e in cls]
