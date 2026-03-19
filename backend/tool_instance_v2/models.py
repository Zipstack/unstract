import uuid

from account_v2.models import User
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
        help_text="Workflow this tool instance belongs to",
    )
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Tool instance UUID",
    )
    tool_id = models.CharField(
        max_length=TOOL_ID_LENGTH,
        db_comment="Function name of the tool being used",
        help_text="Registered tool identifier (Prompt Studio registry ID)",
    )
    input = models.JSONField(
        null=True,
        db_comment="Provisional WF input to a tool",
        help_text="Tool input configuration (JSON)",
    )
    output = models.JSONField(
        null=True,
        db_comment="Provisional WF output to a tool",
        help_text="Tool output configuration (JSON)",
    )
    version = models.CharField(
        max_length=TOOL_VERSION_LENGTH,
        help_text="Tool version",
    )
    metadata = models.JSONField(
        db_comment="Stores config for a tool",
        help_text="Tool configuration and settings (JSON)",
    )
    step = models.IntegerField(help_text="Execution order within the workflow")
    status = models.CharField(
        max_length=TOOL_STATUS_LENGTH,
        default="Ready to start",
        help_text="Current status: PENDING, READY, INITIATED, COMPLETED, or ERROR",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tool_instances_created",
        null=True,
        blank=True,
        help_text="User who created this resource",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tool_instances_modified",
        null=True,
        blank=True,
        help_text="User who last modified this resource",
    )
    objects = ToolInstanceManager()

    class Meta:
        verbose_name = "Tool Instance"
        verbose_name_plural = "Tool Instances"
        db_table = "tool_instance"
