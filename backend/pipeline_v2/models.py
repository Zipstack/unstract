import uuid

from account_v2.models import User
from django.conf import settings
from django.db import models
from django.db.models import Q
from permissions.models import HasMembersMixin, ResourceMemberBase
from tenant_account_v2.organization_member_service import OrganizationMemberService
from utils.models.base_model import BaseModel, BaseModelManager
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from backend.constants import FieldLengthConstants as FieldLength

APP_ID_LENGTH = 32
PIPELINE_NAME_LENGTH = 32


class PipelineModelManager(DefaultOrganizationManagerMixin, BaseModelManager):
    def for_user(self, user):
        """Filter pipelines that the user can access:
        - Pipelines created by the user
        - Pipelines shared with the user
        - Pipelines shared with the entire organization
        - Pipelines shared with any group the user is a member of
        - Service accounts and org admins see all org resources
        """
        if getattr(user, "is_service_account", False):
            return self.all()

        if OrganizationMemberService.is_user_organization_admin(user):
            return self.all()

        # Lazy import — avoids a circular at app load.
        from tenant_account_v2.sharing_helpers import resources_visible_via_groups

        user_group_ids = user.group_memberships.values_list("group_id", flat=True)
        group_shared_ids = resources_visible_via_groups(self.model, user_group_ids)

        return self.filter(
            Q(members=user)  # Owner or direct viewer (created_by is audit-only)
            | Q(shared_to_org=True)  # Shared to entire organization
            | Q(pk__in=group_shared_ids)  # Shared via group membership
        ).distinct()


class Pipeline(HasMembersMixin, DefaultOrganizationMixin, BaseModel):
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
    # Sharing fields
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Whether this pipeline is shared with the entire organization",
    )
    # ``shared_groups`` is stored polymorphically in
    # ``tenant_account_v2.ResourceGroupShare``; the property preserves the
    # ergonomic read surface for DRF / existing callers.

    @property
    def shared_groups(self):
        from tenant_account_v2.sharing_helpers import get_resource_share_groups

        return get_resource_share_groups(self)

    # Owner (and, later, viewer) access lives here via the PipelineMember
    # through model; ``created_by`` is audit-only (UN-2202 co-owners).
    members = models.ManyToManyField(
        User,
        through="PipelineMember",
        related_name="pipelines_member_of",
        help_text="Users with a role (owner/viewer) on this pipeline.",
    )

    # Manager
    objects = PipelineModelManager()

    @property
    def api_key_data(self):
        return {"pipeline": self.id, "description": f"API Key for {self.pipeline_name}"}

    @property
    def api_endpoint(self):
        organization_id = UserContext.get_organization_identifier()
        deployment_endpoint = settings.API_DEPLOYMENT_PATH_PREFIX + "/pipeline/api"
        api_endpoint = f"{deployment_endpoint}/{organization_id}/{self.id}/"
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


class PipelineMember(ResourceMemberBase):
    """Per-user role (owner/viewer) on a ``Pipeline``."""

    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    class Meta:
        db_table = "pipeline_member"
        unique_together = [("user", "pipeline")]
        indexes = [
            models.Index(fields=["pipeline", "role"], name="pipeline_member_role_idx")
        ]
