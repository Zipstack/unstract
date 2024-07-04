import uuid
from typing import Literal

from account.models import User
from django.db import models
from pluggable_apps.apps.chat_history.models import ChatHistory
from pluggable_apps.apps.chat_transcript.enum import Roles
from utils.models.base_model import BaseModel


class ChatTranscript(BaseModel):
    """Model for storing Chat question and answer.

    Args:
        BaseModel (_type_): _description_
    """

    class MessageRole(models.TextChoices):
        USER: tuple[Literal["USER"], Literal["Message from user"]] = (
            "USER",
            "Message from user",
        )
        ASSISTANT = "ASSISTANT", "Message from assistant"

    ROLE_CHOICES = [(role.value, role.name) for role in Roles]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.TextField(
        db_comment="Contains the the actual chat text",
    )
    role = models.CharField(
        choices=ROLE_CHOICES,
        db_comment="Role of the messenger.",
        default=Roles.USER.value,
    )
    chat_history = models.ForeignKey(
        ChatHistory,
        on_delete=models.CASCADE,
        related_name="chat_history_transcript",
        null=False,
        blank=False,
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
