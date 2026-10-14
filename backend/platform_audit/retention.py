import logging
from datetime import datetime, timedelta

from account_v2.models import Organization
from configuration.enums import ConfigKey
from configuration.models import Configuration
from django.utils import timezone

logger = logging.getLogger(__name__)


def retention_days(organization: Organization | None) -> int:
    """The organisation's override of PLATFORM_AUDIT_RETENTION_DAYS, else the default.

    Clamped to the key's 1-3650 bounds. Overrides are validated against them,
    but the env default is not: ``0`` (often meant as "keep forever") would
    otherwise make the purge delete every organisation's history.
    """
    spec = ConfigKey.PLATFORM_AUDIT_RETENTION_DAYS.value
    days = int(
        Configuration.get_value_by_organization(
            ConfigKey.PLATFORM_AUDIT_RETENTION_DAYS, organization
        )
    )
    clamped = min(max(days, spec.min_value), spec.max_value)
    if clamped != days:
        logger.error(
            "PLATFORM_AUDIT_RETENTION_DAYS=%s is outside %s-%s; using %s",
            days,
            spec.min_value,
            spec.max_value,
            clamped,
        )
    return clamped


def retention_cutoff(
    organization: Organization | None, now: datetime | None = None
) -> datetime:
    """Events older than this are expired: hidden from reads, removed by the purge."""
    return (now or timezone.now()) - timedelta(days=retention_days(organization))
