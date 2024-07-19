import uuid

from django.db import models
from prompt_studio.prompt_studio_core.models import CustomTool
from utils.models.base_model import BaseModel


class TagManager(BaseModel):
    """Prompt Studio Tag Manager Model."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Field to store the UUID for the tag manager",
    )
    tool = models.ForeignKey(
        to=CustomTool,
        on_delete=models.CASCADE,
        editable=False,
        null=False,
        blank=False,
        db_comment="Field to store the reference to the tool associated with the tag",
    )
    tag = models.TextField(
        blank=False,
        null=False,
        db_comment="Field to store the tag",
    )

    class Meta:
        db_table = "prompt_studio_tag_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["tool", "tag"],
                name="unique_tool_tag",
            ),
        ]
