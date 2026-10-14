from datetime import datetime, timedelta

from account_v2.models import Organization
from configuration.enums import ConfigKey
from configuration.models import Configuration
from django.utils import timezone


def retention_days(organization: Organization | None) -> int:
    """The organisation's override of PLATFORM_AUDIT_RETENTION_DAYS, else the default."""
    return int(
        Configuration.get_value_by_organization(
            ConfigKey.PLATFORM_AUDIT_RETENTION_DAYS, organization
        )
    )


def retention_cutoff(
    organization: Organization | None, now: datetime | None = None
) -> datetime:
    """Events older than this are expired: hidden from reads, removed by the purge."""
    return (now or timezone.now()) - timedelta(days=retention_days(organization))
