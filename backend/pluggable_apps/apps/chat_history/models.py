import uuid

from account.models import User
from django.db import models
from pluggable_apps.apps.app_deployment.models import AppDeployment
from utils.models.base_model import BaseModel


class ChatHistory(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.TextField(db_comment="Label which shown to user in the chat history")
    app_deployment = models.ForeignKey(
        AppDeployment,
        on_delete=models.CASCADE,
        related_name="app_deployment_chat_history",
        null=False,
        blank=False,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="history_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="history_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
    session_id = models.CharField(
        max_length=128, name="session_id", blank=True, null=True
    )
