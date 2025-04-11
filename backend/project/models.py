import uuid

from account.models import User
from django.db import models
from utils.models.base_model import BaseModel

PROJECT_NAME_SIZE = 128
DESCRIPTION_FIELD_LENGTH = 490


class Project(BaseModel):
    """Stores data related to a project created by a :model:`account.User` in
    an :model:`account.Org`.

    Every org, project is assumed to be unique
    """

    class ProjectIdentifier(models.TextChoices):
        ETL = "ETL", "ETL"
        TASK = "TASK", "TASK"
        DEFAULT = "DEFAULT", "Default"
        APP = "APP", "App"

    project_name = models.CharField(max_length=PROJECT_NAME_SIZE, unique=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_projects",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="modified_projects",
        null=True,
        blank=True,
    )
    settings = models.JSONField(null=True, db_comment="Project settings")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    description = models.TextField(
        null=True, blank=True, max_length=DESCRIPTION_FIELD_LENGTH
    )
    project_status = models.TextField(null=True, blank=True, max_length=PROJECT_NAME_SIZE)
    project_identifier = models.CharField(
        choices=ProjectIdentifier.choices, default=ProjectIdentifier.DEFAULT
    )

    def __str__(self) -> str:
        return f"Projects({self.id}, name: {self.project_name})"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["id", "project_name"], name="unique_project_name"
            ),
        ]
