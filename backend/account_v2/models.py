import uuid

from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models

from account_v2.enums import Product
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
    organization_id = models.CharField(max_length=FieldLength.ORG_NAME_SIZE, unique=True)
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
    restrict_llm_adapter_creation = models.BooleanField(
        default=False,
        db_comment=(
            "Controlled mode: when True, only organization admins may create "
            "LLM adapters in this org. Default False preserves open creation."
        ),
    )
    restrict_connector_creation = models.BooleanField(
        default=False,
        db_comment=(
            "Controlled mode: when True, only organization admins may create "
            "connectors in this org. Default False preserves open creation."
        ),
    )
    # Capability permissions (UN-4399): True means admins only. Defaults keep
    # today's behaviour for each capability.
    restrict_other_adapter_creation = models.BooleanField(
        default=False,
        db_comment=(
            "Capability: when True, only organization admins may create non-LLM "
            "adapters. Default False preserves open creation."
        ),
    )
    restrict_api_key_management = models.BooleanField(
        default=True,
        db_comment=(
            "Capability: when True, only organization admins may create and "
            "rotate platform and global deployment keys. Default True is "
            "today's admin-only behaviour."
        ),
    )
    restrict_member_management = models.BooleanField(
        default=True,
        db_comment=(
            "Capability: when True, only organization admins may invite members "
            "and change roles. Default True is today's admin-only behaviour."
        ),
    )
    restrict_platform_defaults = models.BooleanField(
        default=True,
        db_comment=(
            "Capability: when True, only organization admins may change "
            "organization-wide platform settings. Default True is today's "
            "behaviour."
        ),
    )
    restrict_resource_deletion = models.BooleanField(
        default=False,
        db_comment=(
            "Capability: when True, only organization admins may delete "
            "workflows, API deployments and pipelines. Default False keeps "
            "today's owner-or-admin rule."
        ),
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
    is_deprecated = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Marks old user records when OAuth user changes email",
    )
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

    auth_provider = models.CharField(max_length=64, default="")
    is_service_account = models.BooleanField(
        default=False,
        db_comment="True for service accounts (e.g. platform API key bearer auth sessions)",
    )
    profile_display_name = models.CharField(
        max_length=NAME_SIZE,
        blank=True,
        default="",
        db_comment="Name the user set on their profile; empty means the identity "
        "provider's name is shown",
    )
    language = models.CharField(
        max_length=16, default="en-US", db_comment="Preferred UI language (BCP 47)"
    )
    profile_photo_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        db_comment="When the profile photo was stored; null when there is none",
    )

    def __str__(self):  # type: ignore
        return f"User({self.id}, email: {self.email}, userId: {self.user_id})"

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        db_table = "user"


class UserProductPreference(models.Model):
    """A user's last-used product, shared across their organisations.

    No row means the user has never chosen a product (the first-login flag).
    See ``account_v2/product_preference.py``.
    """

    user = models.OneToOneField(
        "User",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="product_preference",
    )
    product = models.CharField(
        max_length=32,
        choices=Product.choices,
        db_comment="Product id the user last used, e.g. unstract or llm-whisperer",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Product Preference"
        verbose_name_plural = "User Product Preferences"
        db_table = "user_product_preference"
        constraints = [
            models.CheckConstraint(
                check=models.Q(product__in=Product.values),
                name="user_product_preference_product_valid",
            )
        ]


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
        # Server-managed; never accepted as client input.
        editable=False,
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


class SessionRecord(models.Model):
    """Where a user is signed in: one row per live browser session.

    Django's session table cannot be queried by user (the user id is inside the
    encoded payload), so this row is what makes a user's sessions listable.
    Deliberately a plain user FK with no organization scoping: a user's sessions
    span organizations and must all be listed from any one of them. Liveness is
    still owned by `django_session`; a row whose session has expired or gone is
    stale and is pruned when the user's sessions are listed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_key = models.CharField(max_length=40, unique=True)
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="session_records",
    )
    user_agent = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Indexed for the idle sweep at sign-in.
    last_active_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "Session Record"
        verbose_name_plural = "Session Records"
        db_table = "session_record"
