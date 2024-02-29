import uuid

from account.models import User
from apps.app_deployment.models import AppDeployment
from django.db import models
from utils.models.base_model import BaseModel


class ChatHistory(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.TextField()
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
