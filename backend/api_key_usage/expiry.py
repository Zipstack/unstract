"""Optional key expiry, shared by every key type.

A key with no ``expires_at`` never expires and authenticates exactly as before.
"""

from datetime import datetime
from typing import Any

from django.utils import timezone
from platform_audit.actions import Action
from platform_audit.recorder import record_platform_event
from rest_framework import serializers

EXPIRED_MESSAGE = "API key expired"


def is_expired(key: Any, now: datetime | None = None) -> bool:
    """Whether ``key`` has an expiry and it has passed.

    Anything but a datetime counts as no expiry, so a key type without the
    field, or a test double standing in for a key, behaves as it did before.
    """
    expires_at = getattr(key, "expires_at", None)
    return isinstance(expires_at, datetime) and expires_at <= (now or timezone.now())


def validate_expires_at(value: datetime | None) -> datetime | None:
    """Serializer validator: ``None`` clears the expiry, a date must be ahead."""
    if value is not None and value <= timezone.now():
        raise serializers.ValidationError("Expiry must be in the future.")
    return value


def expires_at_field() -> serializers.DateTimeField:
    return serializers.DateTimeField(
        required=False, allow_null=True, validators=[validate_expires_at]
    )


def record_expiry_change(
    request: Any, *, target_type: str, key: Any, before: datetime | None
) -> None:
    """Record ``key.expiry_set`` when a save changed the key's expiry.

    Call it after the save succeeds, with the expiry read before it. Setting,
    changing and clearing all count; an unchanged expiry records nothing.
    """
    after = key.expires_at
    if after == before:
        return
    record_platform_event(
        action=Action.KEY_EXPIRY_SET,
        target_type=target_type,
        target_id=key.id,
        target_name=key.name,
        request=request,
        changes={
            "before": {"expires_at": _iso(before)},
            "after": {"expires_at": _iso(after)},
        },
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
