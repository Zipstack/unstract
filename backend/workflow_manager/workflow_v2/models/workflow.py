import uuid

from account_v2.models import User
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from permissions.models import HasMembersMixin, ResourceMemberBase
from tenant_account_v2.organization_member_service import OrganizationMemberService
from utils.models.base_model import BaseModel, BaseModelManager
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

WORKFLOW_STATUS_LENGTH = 16
DESCRIPTION_FIELD_LENGTH = 490
WORKFLOW_NAME_SIZE = 128


class WorkflowModelManager(DefaultOrganizationManagerMixin, BaseModelManager):
    def for_user(self, user):
        """Filter workflows that the user can access:
        - Workflows created by the user
        - Workflows shared with the user
        - Workflows shared with the entire organization
        - Workflows shared with any group the user is a member of
        - Service accounts and org admins see all org resources
        """
        if getattr(user, "is_service_account", False):
            return self.all()

        if OrganizationMemberService.is_user_organization_admin(user):
            return self.all()

        from tenant_account_v2.sharing_helpers import resources_visible_via_groups

        user_group_ids = user.group_memberships.values_list("group_id", flat=True)
        group_shared_ids = resources_visible_via_groups(self.model, user_group_ids)
        return self.filter(
            Q(members=user)  # Owner or direct viewer (created_by is audit-only)
            | Q(shared_users=user)  # Shared with user
            | Q(shared_to_org=True)  # Shared to entire organization
            | Q(pk__in=group_shared_ids)  # Shared via group membership
        ).distinct()


class Workflow(HasMembersMixin, DefaultOrganizationMixin, BaseModel):
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
    max_file_execution_count = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        db_comment="Maximum times a file can be executed. null=use org/global default. Only enforced for ETL/TASK workflows.",
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

    # Sharing fields
    shared_users = models.ManyToManyField(
        User, related_name="shared_workflows", blank=True
    )
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Whether this workflow is shared with the entire organization",
    )
    # ``shared_groups`` is stored polymorphically in
    # ``tenant_account_v2.ResourceGroupShare``; the property preserves the
    # ergonomic read surface for DRF / existing callers.

    @property
    def shared_groups(self):
        from tenant_account_v2.sharing_helpers import get_resource_share_groups

        return get_resource_share_groups(self)

    # Owner (and, later, viewer) access lives here via the WorkflowMember
    # through model; ``created_by`` is audit-only (UN-2202 co-owners).
    members = models.ManyToManyField(
        User,
        through="WorkflowMember",
        related_name="workflows_member_of",
        help_text="Users with a role (owner/viewer) on this workflow.",
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


class WorkflowMember(ResourceMemberBase):
    """Per-user role (owner/viewer) on a ``Workflow``."""

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    class Meta:
        db_table = "workflow_member"
        unique_together = [("user", "workflow")]
        indexes = [
            models.Index(fields=["workflow", "role"], name="workflow_member_role_idx")
        ]
