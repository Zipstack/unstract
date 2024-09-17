import json
import uuid
from typing import Any

from account.models import User
from connector.fields import ConnectorAuthJSONField
from connector_auth.models import ConnectorAuth
from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models
from project.models import Project
from utils.exceptions import InvalidEncryptionKey
from utils.models.base_model import BaseModel
from workflow_manager.workflow.models import Workflow

from backend.constants import FieldLengthConstants as FLC

CONNECTOR_NAME_SIZE = 128
VERSION_NAME_SIZE = 64


class ConnectorInstance(BaseModel):
    class ConnectorType(models.TextChoices):
        INPUT = "INPUT", "Input"
        OUTPUT = "OUTPUT", "Output"

    class ConnectorMode(models.IntegerChoices):
        UNKNOWN = 0, "UNKNOWN"
        FILE_SYSTEM = 1, "FILE_SYSTEM"
        DATABASE = 2, "DATABASE"
        APPDEPLOYMENT = 3, "APPDEPLOYMENT"
        MANUAL_REVIEW = 4, "MANUAL_REVIEW"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connector_name = models.TextField(
        max_length=CONNECTOR_NAME_SIZE, null=False, blank=False
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="project_connectors",
        null=True,
        blank=True,
    )
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="workflow_connectors",
        null=False,
        blank=False,
    )
    connector_id = models.CharField(max_length=FLC.CONNECTOR_ID_LENGTH, default="")
    # TODO Required to be removed
    connector_metadata = ConnectorAuthJSONField(
        db_column="connector_metadata", null=False, blank=False, default=dict
    )
    connector_metadata_b = models.BinaryField(null=True)
    connector_version = models.CharField(max_length=VERSION_NAME_SIZE, default="")
    connector_type = models.CharField(choices=ConnectorType.choices)
    connector_auth = models.ForeignKey(
        ConnectorAuth, on_delete=models.SET_NULL, null=True, blank=True
    )
    connector_mode = models.CharField(
        choices=ConnectorMode.choices,
        default=ConnectorMode.UNKNOWN,
        db_comment="Choices of connectors",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_connectors",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="modified_connectors",
        null=True,
        blank=True,
    )

    def get_connector_metadata(self) -> dict[str, str]:
        """Gets connector metadata and refreshes the tokens if needed in case
        of OAuth."""
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
            f"Connector({self.id}, type{self.connector_type},"
            f" workflow: {self.workflow})"
        )

    @property
    def metadata(self) -> Any:
        try:
            encryption_secret: str = settings.ENCRYPTION_KEY
            cipher_suite: Fernet = Fernet(encryption_secret.encode("utf-8"))
            decrypted_value = cipher_suite.decrypt(
                bytes(self.connector_metadata_b).decode("utf-8")
            )
        except InvalidToken:
            raise InvalidEncryptionKey(entity=InvalidEncryptionKey.Entity.CONNECTOR)
        return json.loads(decrypted_value)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connector_name", "workflow", "connector_type"],
                name="unique_connector",
            ),
        ]
