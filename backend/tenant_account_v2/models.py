from account_v2.models import Organization, User
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)


class OrganizationMemberModelManager(DefaultOrganizationManagerMixin, models.Manager):
    pass


class OrganizationMember(DefaultOrganizationMixin):
    member_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        default=None,
        related_name="organization_user",
    )
    role = models.CharField()
    is_login_onboarding_msg = models.BooleanField(
        default=True,
        db_comment="Flag to indicate whether the onboarding messages are shown",
    )
    is_prompt_studio_onboarding_msg = models.BooleanField(
        default=True,
        db_comment="Flag to indicate whether the prompt studio messages are shown",
    )

    def __str__(self):  # type: ignore
        return (
            f"OrganizationMember("
            f"{self.member_id}, role: {self.role}, user: {self.user})"
        )

    objects = OrganizationMemberModelManager()

    class Meta:
        db_table = "organization_member"
        verbose_name = "Organization Member"
        verbose_name_plural = "Organization Members"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_organization_member",
            ),
        ]


class OrganizationGroup(BaseModel):
    """Org-scoped collection of users used as a sharing target.

    Org filtering is explicit on every query (no DefaultOrganizationMixin)
    because group CRUD is admin-driven from a request context where
    UserContext is reliably populated — but services and signals that
    touch this model from non-request contexts (e.g. IdP sync) cannot
    depend on UserContext.

    SSO forward-compat fields (`external_id`, `source`, `is_managed_externally`)
    are reserved for IdP sync (Phase 2) and write-locked from the public API.
    """

    SOURCE_LOCAL = "LOCAL"
    SOURCE_IDP = "IDP"
    SOURCE_CHOICES = [
        (SOURCE_LOCAL, "Local"),
        (SOURCE_IDP, "IDP"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="groups"
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_groups",
    )
    external_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_LOCAL)
    is_managed_externally = models.BooleanField(default=False)

    def __str__(self):  # type: ignore
        return f"OrganizationGroup({self.id}, {self.name}, {self.source})"

    class Meta:
        db_table = "organization_group"
        verbose_name = "Organization Group"
        verbose_name_plural = "Organization Groups"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_organization_group_name",
            ),
        ]


class GroupMembership(BaseModel):
    """Explicit through model for OrganizationGroup membership.

    Explicit (instead of implicit M2M) so future fields like ``joined_at``,
    ``role``, or ``invited_by`` can land without a destructive migration.
    The ``(user, group)`` index serves the ``for_user()`` subquery on every
    shareable resource manager.
    """

    group = models.ForeignKey(
        OrganizationGroup, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="group_memberships"
    )

    def __str__(self):  # type: ignore
        return f"GroupMembership(group={self.group_id}, user={self.user_id})"

    class Meta:
        db_table = "organization_group_membership"
        verbose_name = "Group Membership"
        verbose_name_plural = "Group Memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["group", "user"],
                name="unique_group_membership",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "group"]),
        ]
