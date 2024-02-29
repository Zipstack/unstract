import uuid

from account.models import User
from apps.app_deployment.models import AppDeployment
from django.db import models
from utils.models.base_model import BaseModel


class CannedQuestion(BaseModel):
    """Canned Question model stores the canned questions and answers. The
    canned question record is mapped with app_deployment.

    Args:
        BaseModel (_type_): _description_

    Returns:
        _type_: _description_
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.TextField()
    is_active = models.BooleanField(default=True)
    app_deployment = models.ForeignKey(
        AppDeployment,
        on_delete=models.CASCADE,
        related_name="app_deployment_question",
        null=False,
        blank=False,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="question_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="question_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
