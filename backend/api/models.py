import uuid
from typing import Any

from account.models import User
from api.constants import ApiExecution
from django.db import connection, models
from pipeline.models import Pipeline
from utils.models.base_model import BaseModel
from workflow_manager.workflow.models.workflow import Workflow

API_NAME_MAX_LENGTH = 30
DESCRIPTION_MAX_LENGTH = 255
API_ENDPOINT_MAX_LENGTH = 255


class APIDeployment(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(
        max_length=API_NAME_MAX_LENGTH,
        unique=True,
        default="default api",
        db_comment="User-given display name for the API.",
    )
    description = models.CharField(
        max_length=DESCRIPTION_MAX_LENGTH,
        blank=True,
        default="",
        db_comment="User-given description for the API.",
    )
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        db_comment="Foreign key reference to the Workflow model.",
    )
    is_active = models.BooleanField(
        default=True,
        db_comment="Flag indicating whether the API is active or not.",
    )
    # TODO: Implement dynamic generation of API endpoints for API deployments
    # instead of persisting them in the database.
    api_endpoint = models.CharField(
        max_length=API_ENDPOINT_MAX_LENGTH,
        unique=True,
        editable=False,
        db_comment="URL endpoint for the API deployment.",
    )
    api_name = models.CharField(
        max_length=API_NAME_MAX_LENGTH,
        unique=True,
        default="default",
        db_comment="Short name for the API deployment.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="api_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="api_modified_by",
        null=True,
        blank=True,
        editable=False,
    )

    @property
    def api_key_data(self):
        return {"api": self.id, "description": f"API Key for {self.api_name}"}

    def __str__(self) -> str:
        return f"{self.id} - {self.display_name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save hook to update api_endpoint.

        Custom save hook for updating the 'api_endpoint' based on
        'api_name'.     If the instance is being updated, it checks for
        changes in 'api_name'         and adjusts 'api_endpoint'
        accordingly.     If the instance is new, 'api_endpoint' is set
        based on 'api_name'         and the current database schema.
        """
        if self.pk is not None:
            try:
                original = APIDeployment.objects.get(pk=self.pk)
                if original.api_name != self.api_name:
                    org_schema = connection.tenant.schema_name
                    self.api_endpoint = (
                        f"{ApiExecution.PATH}/{org_schema}/{self.api_name}/"
                    )
            except APIDeployment.DoesNotExist:
                org_schema = connection.tenant.schema_name

                self.api_endpoint = f"{ApiExecution.PATH}/{org_schema}/{self.api_name}/"
        super().save(*args, **kwargs)


class APIKey(BaseModel):
    id = models.UUIDField(
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        db_comment="Unique identifier for the API key.",
    )
    api_key = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_comment="Actual key UUID.",
    )
    api = models.ForeignKey(
        APIDeployment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_comment="Foreign key reference to the APIDeployment model.",
    )
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_comment="Foreign key reference to the Pipeline model.",
    )
    description = models.CharField(
        max_length=DESCRIPTION_MAX_LENGTH,
        null=True,
        db_comment="Description of the API key.",
    )
    is_active = models.BooleanField(
        default=True,
        db_comment="Flag indicating whether the API key is active or not.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="api_key_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="api_key_modified_by",
        null=True,
        blank=True,
        editable=False,
    )

    def __str__(self) -> str:
        return f"{self.api.api_name} - {self.id} - {self.api_key}"
