import logging
from datetime import datetime, timedelta

from account_v2.models import Organization
from configuration.enums import ConfigKey
from configuration.models import Configuration
from django.utils import timezone

logger = logging.getLogger(__name__)


def retention_days(organization: Organization | None) -> int:
    """The organisation's override of PLATFORM_AUDIT_RETENTION_DAYS, else the default.

    The env default is not validated by ``Configuration``, so it is checked
    here and fails closed: a value outside 1-3650 (``0`` is often meant as
    "keep forever") becomes the maximum. Hiding too little is reversible; a
    purge acting on a too-short retention is not.

    An org override outside the bounds never reaches this check:
    ``Configuration`` rejects it and returns the env default instead, which may
    be shorter than the operator meant.
    """
    spec = ConfigKey.PLATFORM_AUDIT_RETENTION_DAYS.value
    days = int(
        Configuration.get_value_by_organization(
            ConfigKey.PLATFORM_AUDIT_RETENTION_DAYS, organization
        )
    )
    clamped = days if spec.min_value <= days <= spec.max_value else spec.max_value
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
