import logging
import uuid
from typing import Any

from account_v2.models import User
from adapter_processor_v2.models import AdapterInstance
from django.db import models
from django.db.models import QuerySet
from utils.file_storage.constants import FileStorageKeys
from utils.file_storage.helpers.prompt_studio_file_helper import PromptStudioFileHelper
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

from prompt_studio.prompt_studio_core_v2.constants import DefaultPrompts
from unstract.sdk1.file_storage.constants import StorageType
from unstract.sdk1.file_storage.env_helper import EnvHelper

logger = logging.getLogger(__name__)


class CustomToolModelManager(DefaultOrganizationManagerMixin, models.Manager):
    def for_user(self, user: User) -> QuerySet[Any]:
        return (
            self.get_queryset()
            .filter(
                models.Q(created_by=user)
                | models.Q(shared_users=user)
                | models.Q(shared_to_org=True)
            )
            .distinct("tool_id")
        )


class CustomTool(DefaultOrganizationMixin, BaseModel):
    """Model to store the custom tools designed in the tool studio."""

    tool_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, help_text="Project UUID"
    )
    tool_name = models.TextField(
        blank=False,
        null=False,
        help_text="Display name of the Prompt Studio project",
    )
    description = models.TextField(
        blank=False,
        null=False,
        help_text="Project description",
    )
    author = models.TextField(
        blank=False,
        null=False,
        db_comment="Specific to the user who created the tool.",
        help_text="Author of the project",
    )
    icon = models.TextField(
        blank=True,
        db_comment="Field to store \
            icon url for the custom tool.",
        help_text="Icon identifier",
    )
    output = models.TextField(
        db_comment="Field to store the output format type.",
        blank=True,
        help_text="Default output configuration",
    )
    log_id = models.UUIDField(
        default=uuid.uuid4,
        db_comment="Field to store unique log_id for polling",
        help_text="Associated log identifier",
    )

    summarize_context = models.BooleanField(
        default=False,
        db_comment="Flag to summarize content",
        help_text="Whether to use context summarization",
    )
    summarize_as_source = models.BooleanField(
        default=False,
        db_comment="Flag to use summarized content as source",
        help_text="Whether to use summarized text as source",
    )
    summarize_prompt = models.TextField(
        blank=True,
        db_comment="Field to store the summarize prompt",
        unique=False,
        help_text="Prompt used for context summarization",
    )
    summarize_llm_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        db_comment="Field to store the LLM adapter for summarization",
        null=True,
        blank=True,
        related_name="summarize_enabled_custom_tools",
        help_text="LLM adapter used for context summarization",
    )
    preamble = models.TextField(
        blank=True,
        db_comment="Preamble to the prompts",
        default=DefaultPrompts.PREAMBLE,
        help_text="Text prepended to all prompts",
    )
    postamble = models.TextField(
        blank=True,
        db_comment="Appended as postable to prompts.",
        default=DefaultPrompts.POSTAMBLE,
        help_text="Text appended to all prompts",
    )
    prompt_grammer = models.JSONField(
        null=True,
        blank=True,
        db_comment="Synonymous words used in prompt",
        help_text="Grammar/synonym mappings for prompt normalization",
    )
    monitor_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        db_comment="Field to store monitor llm",
        null=True,
        blank=True,
        related_name="custom_tools_monitor",
        help_text="LLM adapter used for monitoring/evaluation",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="custom_tools_created",
        help_text="User who created this resource",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="custom_tools_modified",
        help_text="User who last modified this resource",
    )

    exclude_failed = models.BooleanField(
        db_comment="Flag to make the answer null if it is incorrect",
        default=True,
        help_text="Whether to exclude failed extractions from output",
    )
    single_pass_extraction_mode = models.BooleanField(
        db_comment="Flag to enable or disable single pass extraction mode",
        default=False,
        help_text="Whether single-pass extraction is enabled",
    )
    challenge_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        db_comment="Field to store challenge llm",
        null=True,
        blank=True,
        related_name="custom_tools_challenge",
        help_text="LLM adapter used for challenge/verification",
    )
    enable_challenge = models.BooleanField(
        db_comment="Flag to enable or disable challenge",
        default=False,
        help_text="Whether LLM challenge/verification is enabled",
    )
    enable_highlight = models.BooleanField(
        db_comment="Flag to enable or disable document highlighting",
        default=False,
        help_text="Whether document highlighting is enabled",
    )
    enable_word_confidence = models.BooleanField(
        db_comment="Flag to enable or disable word-level confidence (depends on enable_highlight)",
        default=False,
        help_text="Whether word-level confidence scoring is enabled",
    )
    custom_data = models.JSONField(
        null=True,
        blank=True,
        db_comment="Custom data for variable replacement in prompts using {{custom_data.key}} syntax",
        help_text="Custom key-value data for variable replacement in prompts",
    )

    # Introduced field to establish M2M relation between users and custom_tool.
    # This will introduce intermediary table which relates both the models.
    shared_users = models.ManyToManyField(
        User,
        related_name="shared_custom_tools",
        help_text="Users this project is shared with",
    )

    # Field to enable organization-level sharing
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Flag to share this custom tool with all users in the organization",
        help_text="Whether shared with entire organization",
    )

    objects = CustomToolModelManager()

    def delete(self, organization_id=None, *args, **kwargs):
        # Delete the documents associated with the tool
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        file_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
            organization_id,
            is_create=False,
            user_id=self.created_by.user_id,
            tool_id=str(self.tool_id),
        )
        try:
            fs_instance.rm(file_path, True)
        except FileNotFoundError:
            # Supressed to handle cases when the remote
            # file is missing or already deleted
            pass
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Custom Tool"
        verbose_name_plural = "Custom Tools"
        db_table = "custom_tool"
        constraints = [
            models.UniqueConstraint(
                fields=["tool_name", "organization"],
                name="unique_tool_name",
            ),
        ]
