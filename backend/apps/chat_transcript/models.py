import uuid

from account.models import User
from apps.chat_history.models import ChatHistory
from django.db import models
from llama_index.llms.types import MessageRole
from utils.models.base_model import BaseModel


class ChatTranscript(BaseModel):
    """Model for storing Chat question and answer.

    Args:
        BaseModel (_type_): _description_
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.TextField()
    role = models.CharField(
        choices=[(tag.value, tag.name) for tag in MessageRole],
        db_comment="Role of the messenger.",
        editable=False,
        null=False,
    )
    parent_message = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        editable=False,
    )
    chat_history = models.ForeignKey(
        ChatHistory,
        on_delete=models.CASCADE,
        related_name="chat_history_transcript",
        null=False,
        blank=False,
        editable=False,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="transcript_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="transcript_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
