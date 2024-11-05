import uuid

from account.models import User
from django.db import models
from project.models import Project
from utils.models.base_model import BaseModel

WORKFLOW_STATUS_LENGTH = 16
DESCRIPTION_FIELD_LENGTH = 490
WORKFLOW_NAME_SIZE = 128


class Workflow(BaseModel):
    class WorkflowType(models.TextChoices):
        DEFAULT = "DEFAULT", "Not ready yet"
        ETL = "ETL", "ETL pipeline"
        TASK = "TASK", "TASK pipeline"
        API = "API", "API deployment"
        APP = "APP", "App deployment"

    class ExecutionAction(models.TextChoices):
        START = "START", "Start the Execution"
        NEXT = "NEXT", "Execute next tool"
        STOP = "STOP", "Stop the execution"
        CONTINUE = "CONTINUE", "Continue to full execution"

    # TODO Make this guid as primaryId instaed of current id bigint
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="project_workflow",
        null=True,
        blank=True,
    )
    description = models.TextField(max_length=DESCRIPTION_FIELD_LENGTH, default="")
    workflow_name = models.CharField(max_length=WORKFLOW_NAME_SIZE, unique=True)
    is_active = models.BooleanField(default=False)
    status = models.CharField(max_length=WORKFLOW_STATUS_LENGTH, default="")
    llm_response = models.TextField()
    workflow_owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="workflow_owner",
        null=True,
        blank=True,
    )
    deployment_type = models.CharField(
        choices=WorkflowType.choices,
        db_comment="Type of workflow deployment",
        default=WorkflowType.DEFAULT,
    )
    source_settings = models.JSONField(
        null=True, db_comment="Settings for the Source module"
    )
    destination_settings = models.JSONField(
        null=True, db_comment="Settings for the Destination module"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_workflow",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="modified_workflow",
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return f"{self.id}, name: {self.workflow_name}"
