import json
import uuid
from typing import Any

from account_v2.models import User
from connector_auth_v2.models import ConnectorAuth
from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models
from utils.exceptions import InvalidEncryptionKey
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

from backend.constants import FieldLengthConstants as FLC

CONNECTOR_NAME_SIZE = 128
VERSION_NAME_SIZE = 64


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
        blank=True,
    )
    is_shared = models.BooleanField(
        default=True,
        help_text="True for centralized connectors, False for workflow-specific connectors"
    )
    connector_id = models.CharField(max_length=FLC.CONNECTOR_ID_LENGTH, default="")
    connector_metadata = models.BinaryField(null=True)
    connector_version = models.CharField(max_length=VERSION_NAME_SIZE, default="")
    connector_type = models.CharField(choices=ConnectorType.choices)
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

    # TODO: Remove if unused
    def get_connector_metadata(self) -> dict[str, str]:
        """Gets connector metadata and refreshes the tokens if needed in case
        of OAuth.
        """
        tokens_refreshed = False
        if self.connector_auth:
            (
                self.connector_metadata,
                tokens_refreshed,
            ) = self.connector_auth.get_and_refresh_tokens()
        if tokens_refreshed:
            self.save()
        return self.connector_metadata

    @staticmethod
    def supportsOAuth(connector_id: str) -> bool:
        return bool(
            ConnectorProcessor.get_connector_data_with_key(
                connector_id, ConnectorKeys.OAUTH
            )
        )

    def __str__(self) -> str:
        return (
            f"Connector({self.id}, type{self.connector_type}, workflow: {self.workflow})"
        )

    def get_connector_metadata_bytes(self):
        """Convert connector_metadata to bytes if it is a memoryview.

        Returns:
            bytes: The connector_metadata as bytes.
        """
        if isinstance(self.connector_metadata, memoryview):
            return self.connector_metadata.tobytes()
        return self.connector_metadata

    @property
    def metadata(self) -> Any:
        """Decrypt and return the connector metadata as a dictionary.

        This property handles the decryption of the connector_metadata,
        converting it to bytes if necessary, and then loading the decrypted
        JSON string into a dictionary.

        Returns:
            dict: The decrypted connector metadata.
        """
        try:
            connector_metadata_bytes = self.get_connector_metadata_bytes()

            if connector_metadata_bytes is None:
                return None

            if isinstance(connector_metadata_bytes, (dict)):
                return connector_metadata_bytes
            encryption_secret: str = settings.ENCRYPTION_KEY
            cipher_suite: Fernet = Fernet(encryption_secret.encode("utf-8"))
            decrypted_value = cipher_suite.decrypt(connector_metadata_bytes)
        except InvalidToken:
            raise InvalidEncryptionKey(entity=InvalidEncryptionKey.Entity.CONNECTOR)
        return json.loads(decrypted_value.decode("utf-8"))

    class Meta:
        db_table = "connector_instance"
        verbose_name = "Connector Instance"
        verbose_name_plural = "Connector Instances"
        constraints = [
            models.UniqueConstraint(
                fields=["connector_name", "workflow", "connector_type"],
                condition=models.Q(is_shared=False),
                name="unique_workflow_specific_connector",
            ),
            models.UniqueConstraint(
                fields=["connector_name", "organization", "connector_type"],
                condition=models.Q(is_shared=True),
                name="unique_shared_connector",
            ),
        ]
