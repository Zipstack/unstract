import uuid

from account.models import User
from django.db import models
from prompt_studio.prompt_studio.models import CustomTool
from utils.models.base_model import BaseModel

from .fields import (
    ToolMetadataJSONField,
    ToolPropertyJSONField,
    ToolSpecJSONField,
)


class PromptStudioRegistry(BaseModel):
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
    icon = models.CharField(
        db_comment="Tool icon in svg format", editable=False
    )
    url = models.CharField(editable=False)
    custom_tool = models.OneToOneField(
        CustomTool,
        on_delete=models.CASCADE,
        related_name="prompt_studio_registry",
        editable=False,
        null=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_registry_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_registry_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
