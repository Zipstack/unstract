"""Rotate a key's secret with an optional grace period for the old one.

During the grace period both secrets authenticate, so callers can switch over
without downtime. Only the latest old secret is kept: rotating again drops the
one before it, and rotating with no grace cuts off every old secret at once.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from rest_framework import serializers

GRACE_NONE = "none"
GRACE_PERIODS: dict[str, timedelta | None] = {
    GRACE_NONE: None,
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}

# The fields rotate_secret changes, for save(update_fields=...).
ROTATED_FIELDS = ["key", "previous_key", "previous_key_expires_at"]


class RotateSerializer(serializers.Serializer):
    grace = serializers.ChoiceField(choices=list(GRACE_PERIODS), default=GRACE_NONE)


def rotate_secret(key: Any, grace: str, now: datetime | None = None) -> None:
    """Give ``key`` a new secret, keeping the old one valid for ``grace``.

    Changes the instance only; the caller saves ``ROTATED_FIELDS``.
    """
    period = GRACE_PERIODS[grace]
    old = key.key
    key.key = uuid.uuid4()
    if period is None:
        key.previous_key = None
        key.previous_key_expires_at = None
    else:
        key.previous_key = old
        key.previous_key_expires_at = (now or timezone.now()) + period


def grace_summary(key: Any) -> str:
    """Audit summary for a rotation that left the old secret working."""
    if key.previous_key_expires_at is None:
        return ""
    return f"previous secret works until {key.previous_key_expires_at.isoformat()}"


def get_by_secret(queryset: Any, token: Any, now: datetime | None = None, **filters):
    """The key whose current secret, or unexpired previous one, is ``token``.

    Looks up the current secret first, the same query as before rotation had a
    grace period, and tries the previous secret only when that misses. Raises
    the model's ``DoesNotExist`` if neither matches.
    """
    try:
        return queryset.get(key=token, **filters)
    except ObjectDoesNotExist:
        return queryset.get(
            previous_key=token,
            previous_key_expires_at__gt=now or timezone.now(),
            **filters,
        )
