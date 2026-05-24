import uuid

from account_v2.models import User
from adapter_processor_v2.models import AdapterInstance
from django.db import models
from utils.models.base_model import BaseModel, BaseModelManager
from utils.user_context import UserContext

from prompt_studio.prompt_studio_core_v2.exceptions import DefaultProfileError
from prompt_studio.prompt_studio_core_v2.models import CustomTool


class ProfileManagerModelManager(BaseModelManager):
    def for_user(self, user):
        """Mirror the visibility model used by Workflow/Pipeline/etc.

        Without this, ProfileManager rows created by another user (notably
        the service account used by org-to-org migration) are invisible to
        every other org member. Service accounts and org admins see all
        rows within the current org.

        ProfileManager has no direct ``organization`` FK — scope via the
        parent CustomTool so the ``shared_to_org=True`` branch cannot
        leak rows across tenants when a UUID is known/guessed.
        """
        # Service accounts and admins still need to be org-scoped — they
        # otherwise see rows from every org in the DB.
        from django.db.models import Q

        org_scope = Q(prompt_studio_tool__organization=UserContext.get_organization())

        if getattr(user, "is_service_account", False):
            return self.filter(org_scope)

        from tenant_account_v2.organization_member_service import (
            OrganizationMemberService,
        )

        if OrganizationMemberService.is_user_organization_admin(user):
            return self.filter(org_scope)

        return self.filter(
            org_scope
            & (Q(created_by=user) | Q(shared_users=user) | Q(shared_to_org=True))
        ).distinct()


class ProfileManager(BaseModel):
    """Model to store the LLM Triad management details for Prompt."""

    class RetrievalStrategy(models.TextChoices):
        SIMPLE = "simple", "Simple retrieval"
        SUBQUESTION = "subquestion", "Subquestion retrieval"
        FUSION = "fusion", "Fusion retrieval"
        RECURSIVE = "recursive", "Recursive retrieval"
        ROUTER = "router", "Router retrieval"
        KEYWORD_TABLE = "keyword_table", "Keyword table retrieval"
        AUTOMERGING = "automerging", "Auto-merging retrieval"

    profile_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_name = models.TextField(blank=False)
    vector_store = models.ForeignKey(
        AdapterInstance,
        db_comment="Field to store the chosen vector store.",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="profiles_vector_store",
    )
    embedding_model = models.ForeignKey(
        AdapterInstance,
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="profiles_embedding_model",
    )
    llm = models.ForeignKey(
        AdapterInstance,
        db_comment="Field to store the LLM chosen by the user",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="profiles_llm",
    )
    x2text = models.ForeignKey(
        AdapterInstance,
        db_comment="Field to store the X2Text Adapter chosen by the user",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="profiles_x2text",
    )
    chunk_size = models.IntegerField(null=True, blank=True)
    chunk_overlap = models.IntegerField(null=True, blank=True)
    reindex = models.BooleanField(default=False)
    retrieval_strategy = models.TextField(
        choices=RetrievalStrategy.choices,
        blank=True,
        db_comment="Field to store the retrieval strategy for prompts",
        default=RetrievalStrategy.SIMPLE,
    )
    similarity_top_k = models.IntegerField(
        blank=True,
        null=True,
        db_comment="Field to store number of top embeddings to take into context",  # noqa: E501
    )
    section = models.TextField(
        blank=True, null=True, db_comment="Field to store limit to section"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="profile_managers_created",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="profile_managers_modified",
        null=True,
        blank=True,
        editable=False,
    )

    prompt_studio_tool = models.ForeignKey(
        CustomTool, on_delete=models.CASCADE, null=True, related_name="profile_managers"
    )
    is_default = models.BooleanField(
        default=False,
        db_comment="Default LLM Profile used in prompt",
    )

    is_summarize_llm = models.BooleanField(
        default=False,
        db_comment="DEPRECATED: Default LLM Profile used for summarizing. Use CustomTool.summarize_llm_adapter instead.",
    )

    shared_users = models.ManyToManyField(
        User, related_name="shared_profile_managers", blank=True
    )
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Whether this profile is shared with the entire organization",
    )

    objects = ProfileManagerModelManager()

    class Meta:
        verbose_name = "Profile Manager"
        verbose_name_plural = "Profile Managers"
        db_table = "profile_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["prompt_studio_tool", "profile_name"],
                name="unique_prompt_studio_tool_profile_name_index",
            ),
        ]

    @staticmethod
    def get_default_llm_profile(tool: CustomTool) -> "ProfileManager":
        try:
            return ProfileManager.objects.get(  # type: ignore
                prompt_studio_tool=tool, is_default=True
            )
        except ProfileManager.DoesNotExist:
            raise DefaultProfileError
