"""Usage as the key pages show it: status, last use, daily history, callers.

Reads call ``refresh`` first, so counts pending in Redis since the last flush
are included. Days are UTC days, and the window is the last ``RETENTION_DAYS``
of them, today included.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from api_v2.models import APIDeployment
from django.db.models import Max, Sum
from django.utils import timezone

from api_key_usage.constants import (
    EXPIRING_WITHIN_DAYS,
    IDLE_AFTER_DAYS,
    RETENTION_DAYS,
)
from api_key_usage.expiry import is_expired
from api_key_usage.flush import flush_pending_usage, oldest_kept_day
from api_key_usage.models import ApiKeyCallerDaily, ApiKeyLastUsed, ApiKeyUsageDaily
from api_key_usage.registry import key_types

logger = logging.getLogger(__name__)

EXPIRED = "expired"
EXPIRING = "expiring"
NEVER_USED = "never_used"
IDLE = "idle"
ACTIVE = "active"
USAGE_STATUSES = [EXPIRED, EXPIRING, NEVER_USED, IDLE, ACTIVE]


@dataclass(frozen=True)
class KeyUsage:
    last_used_at: datetime | None
    calls_30d: int
    usage_status: str


def refresh() -> None:
    """Flush pending usage so a read is current. A failure only makes it stale."""
    try:
        flush_pending_usage()
    except Exception:
        logger.exception("API key usage flush before a read failed")


def usage_status(key: Any, last_used_at: datetime | None, now: datetime) -> str:
    """The first that applies: expired, expiring, never used, idle, active."""
    if is_expired(key, now):
        return EXPIRED
    expires_at = getattr(key, "expires_at", None)
    if expires_at and expires_at <= now + timedelta(days=EXPIRING_WITHIN_DAYS):
        return EXPIRING
    if last_used_at is None:
        return NEVER_USED
    if last_used_at < now - timedelta(days=IDLE_AFTER_DAYS):
        return IDLE
    return ACTIVE


def usage_by_key(
    key_type: str, keys: Iterable[Any], now: datetime | None = None
) -> dict[Any, KeyUsage]:
    """Usage for each key, by id, in two queries whatever the number of keys."""
    now = now or timezone.now()
    keys = list(keys)
    ids = [key.id for key in keys]
    last_used = dict(
        ApiKeyLastUsed.objects.filter(key_type=key_type, key_id__in=ids).values_list(
            "key_id", "last_used_at"
        )
    )
    calls = dict(
        ApiKeyUsageDaily.objects.filter(
            key_type=key_type, key_id__in=ids, day__gte=oldest_kept_day(now)
        )
        .values("key_id")
        .annotate(total=Sum("calls"))
        .values_list("key_id", "total")
    )
    return {
        key.id: KeyUsage(
            last_used_at=last_used.get(key.id),
            calls_30d=calls.get(key.id, 0),
            usage_status=usage_status(key, last_used.get(key.id), now),
        )
        for key in keys
    }


def daily_history(
    key_type: str, key_id: Any, now: datetime | None = None
) -> list[dict[str, Any]]:
    """One entry per day of the window, oldest first, days without calls as 0."""
    first = oldest_kept_day(now or timezone.now())
    counts: dict[date, int] = dict(
        ApiKeyUsageDaily.objects.filter(
            key_type=key_type, key_id=key_id, day__gte=first
        ).values_list("day", "calls")
    )
    days = (first + timedelta(days=n) for n in range(RETENTION_DAYS))
    return [{"day": day, "calls": counts.get(day, 0)} for day in days]


def callers(
    key_type: str, key_id: Any, organization: Any, now: datetime | None = None
) -> list[dict[str, Any]]:
    """The API deployments the key called in the window, most calls first.

    A deployment deleted since keeps its counts, with no name.
    """
    rows = (
        ApiKeyCallerDaily.objects.filter(
            key_type=key_type,
            key_id=key_id,
            day__gte=oldest_kept_day(now or timezone.now()),
        )
        .values("api_deployment_id")
        .annotate(calls=Sum("calls"), last_call_at=Max("last_call_at"))
        .order_by("-calls", "-last_call_at")
    )
    rows = list(rows)
    deployments = {
        d.id: d
        for d in APIDeployment.objects.filter(
            organization=organization,
            id__in=[row["api_deployment_id"] for row in rows],
        )
    }
    result = []
    for row in rows:
        deployment = deployments.get(row["api_deployment_id"])
        result.append(
            {
                "api_deployment_id": row["api_deployment_id"],
                "display_name": deployment.display_name if deployment else None,
                "api_name": deployment.api_name if deployment else None,
                "calls": row["calls"],
                "last_call_at": row["last_call_at"],
            }
        )
    return result


def summary(organization: Any, now: datetime | None = None) -> dict[str, Any]:
    """Counts of the organisation's active keys that need attention.

    A key counts once, under its usage status, so these match the status the
    key lists show.
    """
    now = now or timezone.now()
    totals = {NEVER_USED: 0, EXPIRING: 0, IDLE: 0}
    by_type = {}
    for key_type in key_types():
        keys = key_type.keys(organization).filter(is_active=True)
        counts = dict.fromkeys(totals, 0)
        for usage in usage_by_key(key_type.name, keys, now).values():
            if usage.usage_status in counts:
                counts[usage.usage_status] += 1
        by_type[str(key_type.name)] = _named(counts)
        for status, count in counts.items():
            totals[status] += count
    return {**_named(totals), "by_type": by_type}


def _named(counts: dict[str, int]) -> dict[str, int]:
    return {
        "never_used": counts[NEVER_USED],
        "expiring_7d": counts[EXPIRING],
        "idle_90d": counts[IDLE],
    }
