import logging
import uuid
from typing import Any

from account_v2.models import User
from adapter_processor_v2.models import AdapterInstance
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import QuerySet
from permissions.models import HasMembersMixin
from tenant_account_v2.organization_member_service import OrganizationMemberService
from tenant_account_v2.sharing_helpers import (
    resources_visible_via_groups,
    resources_visible_via_memberships,
)
from unstract.sdk1.file_storage.constants import StorageType
from unstract.sdk1.file_storage.env_helper import EnvHelper
from utils.file_storage.constants import FileStorageKeys
from utils.file_storage.helpers.prompt_studio_file_helper import PromptStudioFileHelper
from utils.models.base_model import BaseModel, BaseModelManager
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

from prompt_studio.prompt_studio_core_v2.constants import DefaultPrompts

logger = logging.getLogger(__name__)


class CustomToolModelManager(DefaultOrganizationManagerMixin, BaseModelManager):
    def for_user(self, user: User) -> QuerySet[Any]:
        if getattr(user, "is_service_account", False):
            return self.all()

        if OrganizationMemberService.is_user_organization_admin(user):
            return self.all()

        user_group_ids = user.group_memberships.values_list("group_id", flat=True)
        group_shared_ids = resources_visible_via_groups(self.model, user_group_ids)
        member_ids = resources_visible_via_memberships(self.model, user)

        return (
            self.get_queryset()
            .filter(
                models.Q(pk__in=member_ids)
                | models.Q(shared_to_org=True)
                | models.Q(pk__in=group_shared_ids)
            )
            .distinct("tool_id")
        )


class CustomTool(HasMembersMixin, DefaultOrganizationMixin, BaseModel):
    """Model to store the custom tools designed in the tool studio."""

    tool_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool_name = models.TextField(blank=False, null=False)
    description = models.TextField(blank=False, null=False)
    author = models.TextField(
        blank=False,
        null=False,
        db_comment="Specific to the user who created the tool.",
    )
    icon = models.TextField(
        blank=True,
        db_comment="Field to store \
            icon url for the custom tool.",
    )
    output = models.TextField(
        db_comment="Field to store the output format type.",
        blank=True,
    )
    log_id = models.UUIDField(
        default=uuid.uuid4,
        db_comment="Field to store unique log_id for polling",
    )

    summarize_context = models.BooleanField(
        default=False, db_comment="Flag to summarize content"
    )
    summarize_as_source = models.BooleanField(
        default=False, db_comment="Flag to use summarized content as source"
    )
    summarize_prompt = models.TextField(
        blank=True,
        db_comment="Field to store the summarize prompt",
        unique=False,
    )
    summarize_llm_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        db_comment="Field to store the LLM adapter for summarization",
        null=True,
        blank=True,
        related_name="summarize_enabled_custom_tools",
    )
    preamble = models.TextField(
        blank=True,
        db_comment="Preamble to the prompts",
        default=DefaultPrompts.PREAMBLE,
    )
    postamble = models.TextField(
        blank=True,
        db_comment="Appended as postable to prompts.",
        default=DefaultPrompts.POSTAMBLE,
    )
    prompt_grammer = models.JSONField(
        null=True, blank=True, db_comment="Synonymous words used in prompt"
    )
    monitor_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        db_comment="Field to store monitor llm",
        null=True,
        blank=True,
        related_name="custom_tools_monitor",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="custom_tools_created",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="custom_tools_modified",
    )

    exclude_failed = models.BooleanField(
        db_comment="Flag to make the answer null if it is incorrect",
        default=True,
    )
    single_pass_extraction_mode = models.BooleanField(
        db_comment="Flag to enable or disable single pass extraction mode",
        default=False,
    )
    challenge_llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        db_comment="Field to store challenge llm",
        null=True,
        blank=True,
        related_name="custom_tools_challenge",
    )
    enable_challenge = models.BooleanField(
        db_comment="Flag to enable or disable challenge", default=False
    )
    enable_highlight = models.BooleanField(
        db_comment="Flag to enable or disable document highlighting", default=False
    )
    enable_word_confidence = models.BooleanField(
        db_comment="Flag to enable or disable word-level confidence (depends on enable_highlight)",
        default=False,
    )
    custom_data = models.JSONField(
        null=True,
        blank=True,
        db_comment="Custom data for variable replacement in prompts using {{custom_data.key}} syntax",
    )

    # Field to enable organization-level sharing
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Flag to share this custom tool with all users in the organization",
    )
    # ``shared_groups`` is stored polymorphically in
    # ``tenant_account_v2.ResourceGroupShare``; the property below preserves
    # the ergonomic read surface for DRF / existing callers.

    @property
    def shared_groups(self):
        from tenant_account_v2.sharing_helpers import get_resource_share_groups

        return get_resource_share_groups(self)

    # NULL on pre-feature tools; populated on first successful export.
    # Drives staleness checks (e.g. lookup-change banner) without requiring
    # a data backfill.
    last_exported_at = models.DateTimeField(
        null=True,
        blank=True,
        db_comment="Timestamp of the last successful export; NULL if never exported since the field was introduced.",
    )

    # Owner + direct-viewer access lives here (UN-2202): OWNER / VIEWER rows in
    # the polymorphic ``ResourceMembership`` table. ``created_by`` is
    # audit-only; VIEWER rows succeed the former ``shared_users`` M2M.
    memberships = GenericRelation("tenant_account_v2.ResourceMembership")

    objects = CustomToolModelManager()

    def delete(self, organization_id=None, *args, **kwargs):
        # Delete the documents associated with the tool
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        file_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
            organization_id,
            is_create=False,
            user_id=self.created_by.user_id,
            tool_id=str(self.tool_id),
        )
        try:
            fs_instance.rm(file_path, True)
        except FileNotFoundError:
            # Supressed to handle cases when the remote
            # file is missing or already deleted
            pass
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Custom Tool"
        verbose_name_plural = "Custom Tools"
        db_table = "custom_tool"
        constraints = [
            models.UniqueConstraint(
                fields=["tool_name", "organization"],
                name="unique_tool_name",
            ),
        ]
