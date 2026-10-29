from adapter_processor_v2.models import AdapterInstance
from connector_v2.models import ConnectorInstance
from django.db import models
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

from connection_check.constants import MAX_FAILURE_REASON_LENGTH, ConnectionStatus

# A saved profile whose connection can be tested.
Profile = AdapterInstance | ConnectorInstance


class ConnectionTestResult(DefaultOrganizationMixin, models.Model):
    """Latest connection-test outcome of a saved profile.

    Kept off the profile row so recording a test never moves its
    ``modified_at``.
    """

    status = models.CharField(max_length=16, choices=ConnectionStatus.choices())
    tested_at = models.DateTimeField(db_comment="When the latest test started")
    failure_reason = models.CharField(
        max_length=MAX_FAILURE_REASON_LENGTH, null=True, blank=True
    )

    objects = DefaultOrganizationManagerMixin()

    class Meta:
        abstract = True


class AdapterTestResult(ConnectionTestResult):
    profile = models.OneToOneField(
        AdapterInstance,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="test_result",
    )

    class Meta:
        db_table = "adapter_test_result"
        indexes = [
            models.Index(
                fields=["organization", "status"], name="adapter_test_org_status_idx"
            ),
        ]


class ConnectorTestResult(ConnectionTestResult):
    profile = models.OneToOneField(
        ConnectorInstance,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="test_result",
    )

    class Meta:
        db_table = "connector_test_result"
        indexes = [
            models.Index(
                fields=["organization", "status"], name="connector_test_org_status_idx"
            ),
        ]
