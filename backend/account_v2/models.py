import uuid

from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models

from backend.constants import FieldLengthConstants as FieldLength

NAME_SIZE = 64
KEY_SIZE = 64


class Organization(models.Model):
    """Stores data related to an organization.

    The fields created_by and modified_by is updated after a
    :model:`account.User` is created.
    """

    name = models.CharField(max_length=NAME_SIZE)
    display_name = models.CharField(max_length=NAME_SIZE)
    organization_id = models.CharField(
        max_length=FieldLength.ORG_NAME_SIZE, unique=True
    )
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="orgs_created",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="orgs_modified",
        null=True,
        blank=True,
    )
    modified_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now=True)
    allowed_token_limit = models.IntegerField(
        default=-1,
        db_comment="token limit set in case of frition less onbaoarded org",
    )

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        db_table = "organization"


class User(AbstractUser):
    """Stores data related to a user belonging to any organization.

    Every org, user is assumed to be unique.
    """

    # Third Party Authentication User ID
    user_id = models.CharField()
    project_storage_created = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="users_created",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="users_modified",
        null=True,
        blank=True,
    )
    modified_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Specify a unique related_name for the groups field
    groups = models.ManyToManyField(
        Group,
        related_name="users",
        related_query_name="user",
        blank=True,
    )

    # Specify a unique related_name for the user_permissions field
    user_permissions = models.ManyToManyField(
        Permission,
        related_name="users",
        related_query_name="user",
        blank=True,
    )

    def __str__(self):  # type: ignore
        return f"User({self.id}, email: {self.email}, userId: {self.user_id})"

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        db_table = "user"


class PlatformKey(models.Model):
    """Model to hold details of Platform keys.

    Only users with admin role are allowed to perform any operation
    related keys.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.UUIDField(default=uuid.uuid4)
    key_name = models.CharField(max_length=KEY_SIZE, null=False, blank=True, default="")
    is_active = models.BooleanField(default=False)
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.SET_NULL,
        related_name="platform_keys",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="platform_keys_created",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="platform_keys_modified",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Platform Key"
        verbose_name_plural = "Platform Keys"
        db_table = "platform_key"
        constraints = [
            models.UniqueConstraint(
                fields=["key_name", "organization"],
                name="unique_key_name_organization",
            ),
        ]

class GroupRoleMapping(models.Model):
    """Maps Active Directory groups to Auth0 roles.

    This model maintains the mapping between AD groups and Auth0 roles,
    enabling role-based access control synchronization between
    Active Directory and Auth0.
    """
    # tenant_id = models.IntegerField() TODO: Add tenant_id
    ad_group = models.CharField(max_length=255)
    auth0_role = models.CharField(max_length=255)

    class Meta:
        db_table = "group_role_mapping"
        unique_together = ("ad_group", "auth0_role")  # Ensures no duplicate mappings

    def __str__(self) -> str:
        return f"{self.ad_group} -> {self.auth0_role}"
