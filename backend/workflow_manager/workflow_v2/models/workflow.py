import uuid

from account_v2.models import User
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

WORKFLOW_STATUS_LENGTH = 16
DESCRIPTION_FIELD_LENGTH = 490
WORKFLOW_NAME_SIZE = 128


class WorkflowModelManager(DefaultOrganizationManagerMixin, models.Manager):
    pass


class Workflow(DefaultOrganizationMixin, BaseModel):
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
    description = models.TextField(max_length=DESCRIPTION_FIELD_LENGTH, default="")
    workflow_name = models.CharField(max_length=WORKFLOW_NAME_SIZE)
    is_active = models.BooleanField(default=False)
    status = models.CharField(max_length=WORKFLOW_STATUS_LENGTH, default="")
    workflow_owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="workflows_owned",
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
        related_name="workflows_created",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="workflows_modified",
        null=True,
        blank=True,
    )

    # Manager
    objects = WorkflowModelManager()

    def __str__(self) -> str:
        return f"{self.id}, name: {self.workflow_name}"

    class Meta:
        verbose_name = "Workflow"
        verbose_name_plural = "Workflows"
        db_table = "workflow"
        constraints = [
            models.UniqueConstraint(
                fields=["workflow_name", "organization"],
                name="unique_workflow_name",
            ),
        ]
