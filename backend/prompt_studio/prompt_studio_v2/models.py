import uuid

from account_v2.models import User
from django.db import models
from utils.models.base_model import BaseModel

from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.models import CustomTool


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
        LINE_ITEM = (
            "line-item",
            (
                "Response sent as line-item "
                "which is large a JSON output. "
                "If extraction stopped due to token limitation, "
                "we try to continue extraction from where it stopped"
            ),)

    class PromptType(models.TextChoices):
        PROMPT = "PROMPT", "Response sent as Text"
        NOTES = "NOTES", "Response sent as float"

    class Mode(models.TextChoices):
        DEFAULT = "Default", "Default choice for output"

    class RequiredType(models.TextChoices):
        ALL = "all", "All values required"
        ANY = "any", "Any value required"

    prompt_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
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
        related_name="tool_studio_prompts",
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
    required = models.CharField(
        choices=RequiredType.choices,
        null=True,  # Allows the field to store NULL in the database
        blank=True,  # Allows the field to be optional in forms
        default=None,  # Sets the default value to None
        db_comment="Field to store weather the values all values or any \
        values required. This is used for HQR, based on the value approve or finish \
        review",
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
        related_name="tool_studio_prompts_created",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tool_studio_prompts_modified",
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
        verbose_name = "Tool Studio Prompt"
        verbose_name_plural = "Tool Studio Prompts"
        db_table = "tool_studio_prompt"
        constraints = [
            models.UniqueConstraint(
                fields=["prompt_key", "tool_id"],
                name="unique_prompt_key_tool_id_index",
            ),
        ]
