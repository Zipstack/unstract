import uuid

from account_v2.models import User
from connector_v2.models import ConnectorInstance
from django.db import models
from django.db.models import QuerySet
from utils.models.base_model import BaseModel
from workflow_manager.workflow_v2.models.workflow import Workflow

TOOL_ID_LENGTH = 64
TOOL_VERSION_LENGTH = 16
TOOL_STATUS_LENGTH = 32


class ToolInstanceManager(models.Manager):
    def get_instances_for_workflow(self, workflow: uuid.UUID) -> QuerySet["ToolInstance"]:
        return self.filter(workflow=workflow)


class ToolInstance(BaseModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Settings Not Configured"
        READY = "READY", "Ready to Start"
        INITIATED = "INITIATED", "Initialization in Progress"
        COMPLETED = "COMPLETED", "Process Completed"
        ERROR = "ERROR", "Error Encountered"

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="tool_instances",
        null=False,
        blank=False,
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool_id = models.CharField(
        max_length=TOOL_ID_LENGTH,
        db_comment="Function name of the tool being used",
    )
    input = models.JSONField(null=True, db_comment="Provisional WF input to a tool")
    output = models.JSONField(null=True, db_comment="Provisional WF output to a tool")
    version = models.CharField(max_length=TOOL_VERSION_LENGTH)
    metadata = models.JSONField(db_comment="Stores config for a tool")
    step = models.IntegerField()
    # TODO: Make as an enum supporting fixed values once we have clarity
    status = models.CharField(max_length=TOOL_STATUS_LENGTH, default="Ready to start")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tool_instances_created",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tool_instances_modified",
        null=True,
        blank=True,
    )
    # Added these connectors separately
    # for file and db for scalability
    input_file_connector = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.SET_NULL,
        related_name="input_file_connectors",
        null=True,
        blank=True,
    )
    output_file_connector = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.SET_NULL,
        related_name="output_file_connectors",
        null=True,
        blank=True,
    )
    input_db_connector = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.SET_NULL,
        related_name="input_db_connectors",
        null=True,
        blank=True,
    )
    output_db_connector = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.SET_NULL,
        related_name="output_db_connectors",
        null=True,
        blank=True,
    )

    objects = ToolInstanceManager()

    class Meta:
        verbose_name = "Tool Instance"
        verbose_name_plural = "Tool Instances"
        db_table = "tool_instance"
