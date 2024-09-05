import uuid

from account.models import User
from django.db import models
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
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
    context = models.TextField(
        db_comment="Field to store chunks used", editable=True, null=True, blank=True
    )
    challenge_data = models.JSONField(
        db_comment="Field to store challenge data", editable=True, null=True, blank=True
    )
    eval_metrics = models.JSONField(
        db_column="eval_metrics",
        null=False,
        blank=False,
        default=list,
        db_comment="Field to store the evaluation metrics",
    )
    is_single_pass_extract = models.BooleanField(
        default=False,
        db_comment="Is the single pass extraction mode active",
    )
    prompt_id = models.ForeignKey(
        ToolStudioPrompt,
        on_delete=models.CASCADE,
        related_name="prompt_output_linked_prompt",
    )
    document_manager = models.ForeignKey(
        DocumentManager,
        on_delete=models.CASCADE,
        related_name="prompt_output_linked_document_manager",
    )
    profile_manager = models.ForeignKey(
        ProfileManager,
        on_delete=models.CASCADE,
        related_name="prompt_output_linked_prompt",
    )
    tool_id = models.ForeignKey(
        CustomTool,
        on_delete=models.CASCADE,
        related_name="prompt_ouput_linked_tool",
    )
    run_id = models.UUIDField(default=uuid.uuid4, editable=False)
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "prompt_id",
                    "document_manager",
                    "profile_manager",
                    "tool_id",
                    "is_single_pass_extract",
                ],
                name="unique_prompt_output",
            ),
        ]
