from account_v2.models import Organization
from django.db import models


class ApiKeyUsageDaily(models.Model):
    """Calls one API key authenticated on one UTC day.

    ``key_id`` is not a foreign key, so cloud key types fit the same table and
    a deleted key's history goes when it ages out rather than on delete.
    Written only by ``flush.flush_pending_usage``.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="+", editable=False
    )
    key_type = models.CharField(max_length=64)
    key_id = models.UUIDField()
    day = models.DateField(db_comment="UTC day the calls were made")
    calls = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "api_key_usage_daily"
        constraints = [
            models.UniqueConstraint(
                fields=["key_type", "key_id", "day"],
                name="unique_api_key_usage_daily",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "day"], name="api_key_usage_org_day_idx"
            ),
        ]


class ApiKeyCallerDaily(models.Model):
    """Calls one key made through one API deployment on one UTC day.

    Only keys that authenticate an API deployment (global deployment keys)
    have rows here.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="+", editable=False
    )
    key_type = models.CharField(max_length=64)
    key_id = models.UUIDField()
    api_deployment_id = models.UUIDField()
    day = models.DateField(db_comment="UTC day the calls were made")
    calls = models.PositiveIntegerField(default=0)
    last_call_at = models.DateTimeField()

    class Meta:
        db_table = "api_key_caller_daily"
        constraints = [
            models.UniqueConstraint(
                fields=["key_type", "key_id", "api_deployment_id", "day"],
                name="unique_api_key_caller_daily",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "day"], name="api_key_caller_org_day_idx"
            ),
        ]


class ApiKeyLastUsed(models.Model):
    """When a key last authenticated a request. No row means never used."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="+", editable=False
    )
    key_type = models.CharField(max_length=64)
    key_id = models.UUIDField()
    last_used_at = models.DateTimeField()

    class Meta:
        db_table = "api_key_last_used"
        constraints = [
            models.UniqueConstraint(
                fields=["key_type", "key_id"],
                name="unique_api_key_last_used",
            ),
        ]
