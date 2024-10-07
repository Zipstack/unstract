import uuid

from account.models import User
from django.conf import settings
from django.db import connection, models
from utils.models.base_model import BaseModel
from workflow_manager.endpoint.models import WorkflowEndpoint
from workflow_manager.workflow.models.workflow import Workflow

from backend.constants import FieldLengthConstants as FieldLength

APP_ID_LENGTH = 32
PIPELINE_NAME_LENGTH = 32


class Pipeline(BaseModel):
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
    pipeline_name = models.CharField(
        max_length=PIPELINE_NAME_LENGTH, default="", unique=True
    )
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="pipeline_workflows",
        null=False,
        blank=False,
    )
    # Added as text field until a model for App is included.
    app_id = models.TextField(null=True, blank=True, max_length=APP_ID_LENGTH)
    active = models.BooleanField(
        default=False, db_comment="Indicates whether the pipeline is active"
    )
    scheduled = models.BooleanField(
        default=False, db_comment="Indicates whether the pipeline is scheduled"
    )
    cron_string = models.TextField(
        db_comment="UNIX cron string",
        null=True,
        blank=True,
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
        related_name="created_pipeline",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="modified_pipeline",
        null=True,
        blank=True,
    )

    @property
    def api_key_data(self):
        return {"pipeline": self.id, "description": f"API Key for {self.pipeline_name}"}

    @property
    def api_endpoint(self):
        org_schema = connection.tenant.schema_name
        deployment_endpoint = settings.API_DEPLOYMENT_PATH_PREFIX + "/pipeline/api"

        # Check if the WorkflowEndpoint has a connection_type of MANUALREVIEW
        workflow_endpoint = WorkflowEndpoint.objects.filter(
            workflow=self.workflow,
            connection_type=WorkflowEndpoint.ConnectionType.MANUALREVIEW,
        ).first()
        api_endpoint = f"{deployment_endpoint}/{org_schema}/{self.id}/"
        if workflow_endpoint:
            deployment_endpoint = f"mr/api/{org_schema}/approved/result"
            api_endpoint = f"{deployment_endpoint}/{self.workflow_id}/"

        return api_endpoint

    def __str__(self) -> str:
        return (
            f"Pipeline({self.id}) ("
            f"name: {self.pipeline_name}, "
            f"cron string: {self.cron_string}, "
            f"is active: {self.active}, "
            f"is scheduled: {self.scheduled}"
        )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["id", "pipeline_type"],
                name="unique_pipeline",
            ),
        ]

    def is_active(self) -> bool:
        return bool(self.active)
