import uuid
from typing import Any

from account.models import User
from django.db import models
from django.db.models import QuerySet
from utils.models.base_model import BaseModel
from workflow_manager.workflow.models import Workflow

APPLICATION_NAME_MAX_LENGTH = 30

DESCRIPTION_MAX_LENGTH = 255


class AppDeploymentModelManager(models.Manager):

    def for_user(self, user: User) -> QuerySet[Any]:
        return (
            self.get_queryset()
            .filter(models.Q(created_by=user) | models.Q(shared_users=user))
            .distinct("id")
        )


class AppDeployment(BaseModel):
    """App Deployment.

    Args:
        BaseModel (_type_): _description_
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    app_display_name = models.CharField(
        max_length=APPLICATION_NAME_MAX_LENGTH,
        default="api deployment",
        db_comment="User-given name for the Application.",
    )

    app_name = models.CharField(
        max_length=APPLICATION_NAME_MAX_LENGTH,
        unique=True,
        db_comment="Short name for the APP deployment.",
    )

    description = models.CharField(
        max_length=DESCRIPTION_MAX_LENGTH,
        null=True,
        db_comment="User-given description for the Application",
    )

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        db_comment="Foreign key reference to Workflow model.",
    )

    is_active = models.BooleanField(
        default=True,
        db_comment="Flag indicating status is active or not.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="app_deployment_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="app_deployment_modified_by",
        null=True,
        blank=True,
        editable=False,
    )

    # Introduced field to establish M2M relation between users and app_deployment.
    # This will introduce intermediary table which relates both the models.
    shared_users = models.ManyToManyField(User, related_name="shared_app_deployment")

    objects = AppDeploymentModelManager()


class IndexedDocuments(BaseModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    file_name = models.CharField(
        max_length=64,
        null=True,
        db_comment="Name of indexed file",
    )

    document_id = models.CharField(
        max_length=128,
        null=True,
        db_comment="Doc id supplied from multi doc chat",
    )

    app_deployment = models.ForeignKey(
        AppDeployment,
        on_delete=models.CASCADE,
        related_name="indexed_document_app",
        db_comment="Foreign key reference to App Deployment  model.",
    )
