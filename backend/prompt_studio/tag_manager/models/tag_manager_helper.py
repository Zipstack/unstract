import uuid

from django.db import models
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.tag_manager.models import TagManager
from utils.models.base_model import BaseModel


class TagManagerHelper(BaseModel):
    """Prompt Studio Tag Manager Helper Model."""

    class PromptType(models.TextChoices):
        PROMPT = "PROMPT", "Response sent as Text"
        NOTES = "NOTES", "Response sent as float"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Field to store the UUID for the tag manager helper",
    )
    tag_manager = models.ForeignKey(
        TagManager,
        on_delete=models.CASCADE,
        editable=False,
        db_comment="Field to store the tag manager associated with the helper",
    )
    prompt_id = models.ForeignKey(
        ToolStudioPrompt,
        on_delete=models.CASCADE,
        editable=False,
        db_comment="Field to store the prompt associated with the helper",
    )
    sequence_number = models.IntegerField(null=True, blank=True)
    prompt_type = models.TextField(
        blank=True,
        db_comment="Field to store the type of the input prompt",
        choices=PromptType.choices,
    )
    version = models.CharField(max_length=10, db_comment="Version of prompt")

    class Meta:
        db_table = "prompt_studio_tag_manager_helper"
        constraints = [
            models.UniqueConstraint(
                fields=["tag_manager", "prompt_id"],
                name="unique_tag_manager_prompt_id",
            ),
        ]
