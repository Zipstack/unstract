import logging
import shutil
import uuid
from typing import Any

from account.models import User
from adapter_processor.models import AdapterInstance
from django.db import models
from django.db.models import QuerySet
from file_management.file_management_helper import FileManagerHelper
from prompt_studio.prompt_studio_core.constants import DefaultPrompts
from utils.models.base_model import BaseModel

logger = logging.getLogger(__name__)


class CustomToolModelManager(models.Manager):
    def get_queryset(self) -> QuerySet[Any]:
        return super().get_queryset()

    def for_user(self, user: User) -> QuerySet[Any]:
        return (
            self.get_queryset()
            .filter(models.Q(created_by=user) | models.Q(shared_users=user))
            .distinct("tool_id")
        )


class CustomTool(BaseModel):
    """Model to store the custom tools designed in the tool studio."""

    tool_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool_name = models.TextField(unique=True, blank=False, null=False)
    description = models.TextField(blank=False, null=False)
    author = models.TextField(
        blank=False,
        null=False,
        db_comment="Specific to the user who created the tool.",
    )
    icon = models.TextField(
        blank=True,
        db_comment="Field to store \
            icon url for the custom tool.",
    )
    output = models.TextField(
        db_comment="Field to store the output format type.",
        blank=True,
    )
    log_id = models.UUIDField(
        default=uuid.uuid4,
        db_comment="Field to store unique log_id for polling",
    )

    summarize_context = models.BooleanField(
        default=False, db_comment="Flag to summarize content"
    )
    summarize_as_source = models.BooleanField(
        default=False, db_comment="Flag to use summarized content as source"
    )
    summarize_prompt = models.TextField(
        blank=True,
        db_comment="Field to store the summarize prompt",
        unique=False,
    )
    preamble = models.TextField(
        blank=True,
        db_comment="Preamble to the prompts",
        default=DefaultPrompts.PREAMBLE,
    )
    postamble = models.TextField(
        blank=True,
        db_comment="Appended as postable to prompts.",
        default=DefaultPrompts.POSTAMBLE,
    )
    prompt_grammer = models.JSONField(
        null=True, blank=True, db_comment="Synonymous words used in prompt"
    )
    monitor_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        db_comment="Field to store monitor llm",
        null=True,
        blank=True,
        related_name="monitor_customtools",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tool_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tool_modified_by",
        null=True,
        blank=True,
        editable=False,
    )

    exclude_failed = models.BooleanField(
        db_comment="Flag to make the answer null if it is incorrect",
        default=True,
    )
    single_pass_extraction_mode = models.BooleanField(
        db_comment="Flag to enable or disable single pass extraction mode",
        default=False,
    )
    challenge_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        db_comment="Field to store challenge llm",
        null=True,
        blank=True,
        related_name="challenge_customtools",
    )
    enable_challenge = models.BooleanField(
        db_comment="Flag to enable or disable challenge", default=False
    )

    enable_highlight = models.BooleanField(
        db_comment="Flag to enable or disable document highlighting", default=False
    )

    # Introduced field to establish M2M relation between users and custom_tool.
    # This will introduce intermediary table which relates both the models.
    shared_users = models.ManyToManyField(User, related_name="shared_custom_tool")

    objects = CustomToolModelManager()

    def delete(self, organization_id=None, *args, **kwargs):
        # Delete the documents associated with the tool
        file_path = FileManagerHelper.handle_sub_directory_for_tenants(
            organization_id,
            is_create=False,
            user_id=self.created_by.user_id,
            tool_id=str(self.tool_id),
        )
        if organization_id:
            try:
                shutil.rmtree(file_path)
            except FileNotFoundError:
                logger.error(f"The folder {file_path} does not exist.")
            except OSError as e:
                logger.error(f"Error: {file_path} : {e.strerror}")
                # Continue with the deletion of the tool
        super().delete(*args, **kwargs)
