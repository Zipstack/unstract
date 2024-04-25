import uuid

from account.models import User
from django.db import models
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from utils.models.base_model import BaseModel


class TagManager(BaseModel):
    """Model class to store the tags.

    It has many to many relation with ToolStudioPrompt.
    """
    tag_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tag = models.TextField(
        blank=False, db_comment="Field to store the tag", unique=False
    )
    prompts = models.ManyToManyField(ToolStudioPrompt, related_name='tags')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tag_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tag_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
