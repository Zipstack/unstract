import uuid

from account_v2.models import User
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)
from workflow_manager.workflow_v2.models.workflow import Workflow

from backend.constants import FieldLengthConstants as FieldLength

APP_ID_LENGTH = 32
PIPELINE_NAME_LENGTH = 32


class PipelineModelManager(DefaultOrganizationManagerMixin, models.Manager):
    pass


class Pipeline(DefaultOrganizationMixin, BaseModel):
    """Model to hold data related to Pipelines."""

    class PipelineType(models.TextChoices):
        ETL = "ETL", "ETL"
        TASK = "TASK", "TASK"
        DEFAULT = "DEFAULT", "Default"
        APP = "APP", "App"

    class PipelineStatus(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FAILURE = "FAILURE", "Failure"
        INPROGRESS = "INPROGRESS", "Inprogress"
        YET_TO_START = "YET_TO_START", "Yet to start"
        RESTARTING = "RESTARTING", "Restarting"
        PAUSED = "PAUSED", "Paused"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline_name = models.CharField(max_length=PIPELINE_NAME_LENGTH, default="")
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="pipelines",
        null=False,
        blank=False,
    )
    # Added as text field until a model for App is included.
    app_id = models.TextField(null=True, blank=True, max_length=APP_ID_LENGTH)
    active = models.BooleanField(default=False)  # TODO: Add dbcomment
    scheduled = models.BooleanField(default=False)  # TODO: Add dbcomment
    cron_string = models.TextField(
        db_comment="UNIX cron string",
        null=False,
        blank=False,
        max_length=FieldLength.CRON_LENGTH,
    )
    pipeline_type = models.CharField(
        choices=PipelineType.choices, default=PipelineType.DEFAULT
    )
    run_count = models.IntegerField(default=0)
    last_run_time = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(
        choices=PipelineStatus.choices, default=PipelineStatus.YET_TO_START
    )
    app_icon = models.URLField(
        null=True, blank=True, db_comment="Field to store icon url for Apps"
    )
    app_url = models.URLField(
        null=True, blank=True, db_comment="Stores deployed URL for App"
    )
    # TODO: Change this to a Forgein key once the bundle is created.
    access_control_bundle_id = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="pipelines_created",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="pipelines_modified",
        null=True,
        blank=True,
    )

    # Manager
    objects = PipelineModelManager()

    def __str__(self) -> str:
        return f"Pipeline({self.id})"

    class Meta:
        verbose_name = "Pipeline"
        verbose_name_plural = "Pipelines"
        db_table = "pipeline"
        constraints = [
            models.UniqueConstraint(
                fields=["id", "pipeline_type"],
                name="unique_pipeline_entity",
            ),
            models.UniqueConstraint(
                fields=["pipeline_name", "organization"],
                name="unique_pipeline_name",
            ),
        ]

    def is_active(self) -> bool:
        return bool(self.active)
