import logging
import uuid
from typing import Any

from account_v2.models import User
from django.db import models
from django.db.models import QuerySet
from prompt_studio.prompt_studio_registry_v2.fields import (
    ToolMetadataJSONField,
    ToolPropertyJSONField,
    ToolSpecJSONField,
)
from prompt_studio.prompt_studio_v2.models import CustomTool
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

logger = logging.getLogger(__name__)


class PromptStudioRegistryModelManager(DefaultOrganizationManagerMixin, models.Manager):
    def get_queryset(self) -> QuerySet[Any]:
        return super().get_queryset()

    def list_tools(self, user: User) -> QuerySet[Any]:
        return (
            self.get_queryset()
            .filter(
                models.Q(created_by=user)
                | models.Q(shared_users=user)
                | models.Q(shared_to_org=True)
            )
            .distinct("prompt_registry_id")
        )


class PromptStudioRegistry(DefaultOrganizationMixin, BaseModel):
    """Data model to export JSON fields needed for registering the Custom tool
    to the tool registry.

    By default the tools will be added to private tool hub.
    """

    prompt_registry_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    name = models.CharField(editable=False, default="")
    description = models.CharField(editable=False, default="")
    tool_property = ToolPropertyJSONField(
        db_column="tool_property",
        db_comment="PROPERTIES of the tool",
        null=False,
        blank=False,
        default=dict,
    )
    tool_spec = ToolSpecJSONField(
        db_column="tool_spec",
        db_comment="SPEC of the tool",
        null=False,
        blank=False,
        default=dict,
    )
    tool_metadata = ToolMetadataJSONField(
        db_column="tool_metadata",
        db_comment="Metadata from Prompt Studio",
        null=False,
        blank=False,
        default=dict,
    )
    icon = models.CharField(db_comment="Tool icon in svg format", editable=False)
    url = models.CharField(editable=False)
    custom_tool = models.OneToOneField(
        CustomTool,
        on_delete=models.CASCADE,
        related_name="prompt_studio_registries",
        editable=False,
        null=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_registries_created",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_registries_modified",
        null=True,
        blank=True,
        editable=False,
    )
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Is the exported tool shared with entire org",
    )
    # Introduced field to establish M2M relation between users and tools.
    # This will introduce intermediary table which relates both the models.
    shared_users = models.ManyToManyField(User, related_name="prompt_registries")

    objects = PromptStudioRegistryModelManager()

    class Meta:
        verbose_name = "Prompt Studio Registry"
        verbose_name_plural = "Prompt Studio Registries"
        db_table = "prompt_studio_registry"
