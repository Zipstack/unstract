import uuid

from account_v2.models import User
from django.db import models
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
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
    highlight_data = models.JSONField(
        db_comment="Field to store highlight data", editable=True, null=True, blank=True
    )
    confidence_data = models.JSONField(
        db_comment="Field to store confidence data",
        editable=True,
        null=True,
        blank=True,
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
        related_name="prompt_studio_outputs",
    )
    document_manager = models.ForeignKey(
        DocumentManager,
        on_delete=models.CASCADE,
        related_name="prompt_studio_outputs",
    )
    profile_manager = models.ForeignKey(
        ProfileManager,
        on_delete=models.CASCADE,
        related_name="prompt_studio_outputs",
    )
    tool_id = models.ForeignKey(
        CustomTool,
        on_delete=models.CASCADE,
        related_name="prompt_studio_outputs",
    )
    run_id = models.UUIDField(default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_studio_outputs_created",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_studio_outputs_modified",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Prompt Studio Output Manager"
        verbose_name_plural = "Prompt Studio Output Managers"
        db_table = "prompt_studio_output_manager"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "prompt_id",
                    "document_manager",
                    "profile_manager",
                    "tool_id",
                    "is_single_pass_extract",
                ],
                name="unique_prompt_output_index",
            ),
        ]
