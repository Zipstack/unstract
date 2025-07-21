import logging
import uuid
from typing import Any

from account_v2.models import User
from connector_auth_v2.models import ConnectorAuth
from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from django.db import models
from utils.fields import EncryptedBinaryField
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

from backend.constants import FieldLengthConstants as FLC

CONNECTOR_NAME_SIZE = 128
VERSION_NAME_SIZE = 64

logger = logging.getLogger(__name__)


class ConnectorInstanceModelManager(DefaultOrganizationManagerMixin, models.Manager):
    pass


class ConnectorInstance(DefaultOrganizationMixin, BaseModel):
    # TODO: handle all cascade deletions
    class ConnectorType(models.TextChoices):
        INPUT = "INPUT", "Input"
        OUTPUT = "OUTPUT", "Output"

    class ConnectorMode(models.IntegerChoices):
        UNKNOWN = 0, "UNKNOWN"
        FILE_SYSTEM = 1, "FILE_SYSTEM"
        DATABASE = 2, "DATABASE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connector_name = models.TextField(
        max_length=CONNECTOR_NAME_SIZE, null=False, blank=False
    )
    workflow = models.ForeignKey(
        "workflow_v2.Workflow",
        on_delete=models.CASCADE,
        related_name="connector_workflow",
        null=True,
        blank=False,
    )
    connector_id = models.CharField(max_length=FLC.CONNECTOR_ID_LENGTH, default="")
    connector_metadata = EncryptedBinaryField(null=True)
    connector_version = models.CharField(max_length=VERSION_NAME_SIZE, default="")
    connector_type = models.CharField(choices=ConnectorType.choices, null=True)
    # TODO: handle connector_auth cascade deletion
    connector_auth = models.ForeignKey(
        ConnectorAuth,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connector_instances",
    )
    connector_mode = models.CharField(
        choices=ConnectorMode.choices,
        default=ConnectorMode.UNKNOWN,
        db_comment="0: UNKNOWN, 1: FILE_SYSTEM, 2: DATABASE",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="connectors_created",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="connectors_modified",
        null=True,
        blank=True,
    )

    # Manager
    objects = ConnectorInstanceModelManager()

    @staticmethod
    def supportsOAuth(connector_id: str) -> bool:
        return bool(
            ConnectorProcessor.get_connector_data_with_key(
                connector_id, ConnectorKeys.OAUTH
            )
        )

    def __str__(self) -> str:
        return (
            f"Connector({self.id}, ID={self.connector_id}, mode: {self.connector_mode})"
        )

    @property
    def metadata(self) -> Any:
        """Decrypt and return the connector metadata as a dictionary.

        This property handles the decryption of the connector_metadata,
        converting it to bytes if necessary, and then loading the decrypted
        JSON string into a dictionary.

        Returns:
            dict: The decrypted connector metadata.

        .. deprecated::
            This property is deprecated. Use `connector_metadata` field directly instead.
            This property will be removed in a future version.
        """
        import warnings

        warnings.warn(
            "The 'metadata' property is deprecated. Use 'connector_metadata' field directly instead. "
            "This property will be removed in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.connector_metadata

    class Meta:
        db_table = "connector_instance"
        verbose_name = "Connector Instance"
        verbose_name_plural = "Connector Instances"
        constraints = [
            models.UniqueConstraint(
                fields=["connector_name", "workflow", "connector_type"],
                name="unique_workflow_connector",
            ),
        ]
