import uuid

from account.models import User
from django.db import models
from prompt_studio.prompt_profile_manager.models import ProfileManager
from utils.models.base_model import BaseModel


class CustomTool(BaseModel):
    """Model to store the custom tools designed in the tool studio."""

    tool_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
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
    preamble = models.TextField(
        blank=True, db_comment="Preamble to the prompts"
    )
    postamble = models.TextField(
        blank=True, db_comment="Appended as postable to prompts."
    )
    default_profile = models.ForeignKey(
        ProfileManager,
        on_delete=models.SET_NULL,
        related_name="default_profile",
        null=True,
        blank=True,
    )
    prompt_grammer = models.JSONField(
        null=True, blank=True, db_comment="Synonymous words used in prompt"
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
