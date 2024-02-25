import uuid

from account.models import User
from django.db import models
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.models import CustomTool
from utils.models.base_model import BaseModel


class PromptStudioOutputManager(BaseModel):
    """Data model to handle output persisitance for Project.

    By default the tools will be added to private tool hub.
    """

    prompt_output_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    output = models.CharField(
        db_comment="Field to store output", editable=True, null=True, blank=True
    )

    doc_name = models.CharField(
        db_comment="Field to store the document name",
        editable=True,
    )

    tool_id = models.ForeignKey(
        CustomTool,
        on_delete=models.SET_NULL,
        related_name="prompt_ouput_linked_tool",
        null=True,
        blank=True,
    )
    prompt_id = models.ForeignKey(
        ToolStudioPrompt,
        on_delete=models.SET_NULL,
        related_name="prompt_output_linked_prompt",
        null=True,
        blank=True,
    )
    profile_manager = models.ForeignKey(
        ProfileManager,
        on_delete=models.SET_NULL,
        related_name="prompt_output_linked_prompt",
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_output_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_output_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
