import uuid

from account_v2.models import User
from django.conf import settings
from django.core.validators import MinValueValidator
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
    def for_user(self, user):
        """Filter workflows that the user can access:
        - Workflows created by the user
        - Workflows shared with the user
        - Workflows shared with the entire organization
        """
        from django.db.models import Q

        return self.filter(
            Q(created_by=user)  # Owned by user
            | Q(shared_users=user)  # Shared with user
            | Q(shared_to_org=True)  # Shared to entire organization
        ).distinct()


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
    description = models.TextField(
        max_length=DESCRIPTION_FIELD_LENGTH,
        default="",
        help_text="Optional description",
    )
    workflow_name = models.CharField(
        max_length=WORKFLOW_NAME_SIZE,
        help_text="Display name of the workflow",
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Whether the workflow is currently active",
    )
    status = models.CharField(
        max_length=WORKFLOW_STATUS_LENGTH,
        default="",
        help_text="Current workflow status",
    )
    workflow_owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="workflows_owned",
        null=True,
        blank=True,
        help_text="Owner of the workflow",
    )
    deployment_type = models.CharField(
        choices=WorkflowType.choices,
        db_comment="Type of workflow deployment",
        default=WorkflowType.DEFAULT,
        help_text="Deployment type: DEFAULT, ETL, TASK, API, or APP",
    )
    source_settings = models.JSONField(
        null=True,
        db_comment="Settings for the Source module",
        help_text="Source connector configuration (JSON)",
    )
    destination_settings = models.JSONField(
        null=True,
        db_comment="Settings for the Destination module",
        help_text="Destination connector configuration (JSON)",
    )
    max_file_execution_count = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        db_comment="Maximum times a file can be executed. null=use org/global default. Only enforced for ETL/TASK workflows.",
        help_text="Maximum times a file can be re-executed",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="workflows_created",
        null=True,
        blank=True,
        help_text="User who created this resource",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="workflows_modified",
        null=True,
        blank=True,
        help_text="User who last modified this resource",
    )

    # Sharing fields
    shared_users = models.ManyToManyField(
        User, related_name="shared_workflows", blank=True
    )
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Whether this workflow is shared with the entire organization",
        help_text="Whether shared with entire organization",
    )

    # Manager
    objects = WorkflowModelManager()

    def __str__(self) -> str:
        return f"{self.id}, name: {self.workflow_name}"

    def get_max_execution_count(self) -> int:
        """Get maximum execution count from configuration hierarchy.

        Priority: workflow setting > organization setting > global Django setting

        Returns:
            int: Maximum execution count limit.
        """
        # Check workflow-level setting first
        if self.max_file_execution_count is not None:
            return self.max_file_execution_count

        # Fall back to global Django setting (from backend.settings.execution_config)
        return settings.MAX_FILE_EXECUTION_COUNT

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
