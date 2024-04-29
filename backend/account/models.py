import uuid

from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django_tenants.models import DomainMixin, TenantMixin

from backend.constants import FieldLengthConstants as FieldLength

NAME_SIZE = 64
KEY_SIZE = 64


class Organization(TenantMixin):
    """Stores data related to an organization.

    The fields created_by and modified_by is updated after a
    :model:`account.User` is created.
    """

    name = models.CharField(max_length=NAME_SIZE)
    display_name = models.CharField(max_length=NAME_SIZE)
    organization_id = models.CharField(max_length=FieldLength.ORG_NAME_SIZE)
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="created_orgs",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="modified_orgs",
        null=True,
        blank=True,
    )
    modified_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now=True)
    allowed_token_limit = models.IntegerField(
        default=-1,
        db_comment="token limit set in case of frition less onbaoarded org",
    )

    auto_create_schema = True


class Domain(DomainMixin):
    pass


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
        related_name="created_users",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="modified_users",
        null=True,
        blank=True,
    )
    modified_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Specify a unique related_name for the groups field
    groups = models.ManyToManyField(
        Group,
        related_name="customuser_set",
        related_query_name="customuser",
        blank=True,
    )

    # Specify a unique related_name for the user_permissions field
    user_permissions = models.ManyToManyField(
        Permission,
        related_name="customuser_set",
        related_query_name="customuser",
        blank=True,
    )

    def __str__(self):  # type: ignore
        return f"User({self.id}, email: {self.email}, userId: {self.user_id})"


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
        related_name="related_org",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="created_keys",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="modified_keys",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["key_name", "organization"],
                name="unique_key_name",
            ),
        ]
