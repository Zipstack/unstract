from account_v2.models import Organization, User
from django.contrib.contenttypes.models import ContentType
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
    UserContext is reliably populated.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="groups",
        # Server-managed; never accepted as client input.
        editable=False,
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

    def __str__(self):  # type: ignore
        return f"OrganizationGroup({self.id}, {self.name})"

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


class ResourceGroupShare(BaseModel):
    """Polymorphic group→resource share row.

    Replaces the per-resource ``shared_groups`` M2M join tables with a
    single table covering every shareable resource. One row per
    ``(group, resource)`` edge. Multi-tenancy is enforced by the explicit
    ``organization`` FK plus viewset-level filtering on every read path.
    """

    group = models.ForeignKey(
        OrganizationGroup,
        on_delete=models.CASCADE,
        related_name="resource_shares",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # ``object_id`` is the resource PK as text; every in-scope resource uses
    # UUID primary keys but the column stays varchar to keep the schema open
    # for future non-UUID resources.
    object_id = models.CharField(max_length=255)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="resource_group_shares",
        # Server-managed; never accepted as client input.
        editable=False,
    )

    class Meta:
        db_table = "resource_group_share"
        verbose_name = "Resource Group Share"
        verbose_name_plural = "Resource Group Shares"
        constraints = [
            models.UniqueConstraint(
                fields=["group", "content_type", "object_id"],
                name="uniq_resource_group_share",
            ),
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["organization", "group"]),
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
