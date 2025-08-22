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
    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset()

    def for_user(self, user: User) -> models.QuerySet:
        return (
            self.get_queryset()
            .filter(
                models.Q(created_by=user)
                | models.Q(shared_users=user)
                | models.Q(shared_to_org=True)
            )
            .distinct("id")
        )


class ConnectorInstance(DefaultOrganizationMixin, BaseModel):
    class ConnectorType(models.TextChoices):
        INPUT = "INPUT", "Input"
        OUTPUT = "OUTPUT", "Output"

    class ConnectorMode(models.TextChoices):
        UNKNOWN = "UNKNOWN", "UNKNOWN"
        FILE_SYSTEM = "FILE_SYSTEM", "FILE_SYSTEM"
        DATABASE = "DATABASE", "DATABASE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connector_name = models.TextField(
        max_length=CONNECTOR_NAME_SIZE, null=False, blank=False
    )
    connector_id = models.CharField(max_length=FLC.CONNECTOR_ID_LENGTH, default="")
    connector_metadata = EncryptedBinaryField(null=True)
    connector_version = models.CharField(max_length=VERSION_NAME_SIZE, default="")
    # TODO: handle connector_auth cascade deletion
    connector_auth = models.ForeignKey(
        ConnectorAuth,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connector_instances",
    )
    # TODO: Remove unused connector_mode field, resolved from the ConnectorKit instead
    connector_mode = models.CharField(
        choices=ConnectorMode.choices,
        default=ConnectorMode.UNKNOWN,
        db_comment="0: UNKNOWN, 1: FILE_SYSTEM, 2: DATABASE",
        null=True,
        blank=True,
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

    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Is the connector shared to entire org",
    )

    # Introduced field to establish M2M relation between users and connectors.
    # This will introduce intermediary table which relates both the models.
    shared_users = models.ManyToManyField(
        User, related_name="shared_connectors", blank=True
    )

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
            f"Connector(pk={self.id}, name={self.connector_name}, ID={self.connector_id})"
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
                fields=["connector_name", "organization"],
                name="unique_organization_connector",
            ),
        ]
