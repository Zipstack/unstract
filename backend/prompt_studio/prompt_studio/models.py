import uuid

from account.models import User
from django.db import models
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio_core.models import CustomTool
from utils.models.base_model import BaseModel


class ToolStudioPrompt(BaseModel):
    """Model class while store Prompt data for Custom Tool Studio.

    It has Many to one relation with CustomTool for ToolStudio.
    """

    class EnforceType(models.TextChoices):
        TEXT = "Text", "Response sent as Text"
        NUMBER = "number", "Response sent as number"
        EMAIL = "email", "Response sent as email"
        DATE = "date", "Response sent as date"
        BOOLEAN = "boolean", "Response sent as boolean"
        JSON = "json", "Response sent as json"
        TABLE = "table", "Response sent as table"
        RECORD = "record", "Response sent for records"

    class PromptType(models.TextChoices):
        PROMPT = "PROMPT", "Response sent as Text"
        NOTES = "NOTES", "Response sent as float"

    class Mode(models.TextChoices):
        DEFAULT = "Default", "Default choice for output"

    prompt_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prompt_key = models.TextField(
        blank=False,
        db_comment="Field to store the prompt key",
    )
    enforce_type = models.TextField(
        blank=True,
        db_comment="Field to store the type in \
            which the response to be returned.",
        choices=EnforceType.choices,
        default=EnforceType.TEXT,
    )
    prompt = models.TextField(
        blank=True, db_comment="Field to store the prompt", unique=False
    )
    tool_id = models.ForeignKey(
        CustomTool,
        on_delete=models.SET_NULL,
        related_name="mapped_prompt",
        null=True,
        blank=True,
    )
    sequence_number = models.IntegerField(null=True, blank=True)
    prompt_type = models.TextField(
        blank=True,
        db_comment="Field to store the type of the input prompt",
        choices=PromptType.choices,
    )
    profile_manager = models.ForeignKey(
        ProfileManager,
        on_delete=models.SET_NULL,
        related_name="prompt_profile_manager",
        null=True,
        blank=True,
    )
    output = models.TextField(blank=True)
    # TODO: Remove below 3 fields related to assertion
    assert_prompt = models.TextField(
        blank=True,
        null=True,
        db_comment="Field to store the asserted prompt",
        unique=False,
    )
    assertion_failure_prompt = models.TextField(
        blank=True,
        null=True,
        db_comment="Field to store the prompt key",
        unique=False,
    )
    is_assert = models.BooleanField(default=False)
    active = models.BooleanField(default=True, null=False, blank=False)
    output_metadata = models.JSONField(
        db_column="output_metadata",
        null=False,
        blank=False,
        default=dict,
        db_comment="JSON adapter metadata for the FE to load the pagination",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
    # Eval settings for the prompt
    # NOTE:
    # - Field name format is eval_<metric_type>_<metric_name>
    # - Metric name alone should be UNIQUE across all eval metrics
    evaluate = models.BooleanField(default=True)
    eval_quality_faithfulness = models.BooleanField(default=True)
    eval_quality_correctness = models.BooleanField(default=True)
    eval_quality_relevance = models.BooleanField(default=True)
    eval_security_pii = models.BooleanField(default=True)
    eval_guidance_toxicity = models.BooleanField(default=True)
    eval_guidance_completeness = models.BooleanField(default=True)
    #

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["prompt_key", "tool_id"],
                name="unique_prompt_key_tool_id",
            ),
        ]
