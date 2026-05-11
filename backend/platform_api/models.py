import uuid

from account_v2.models import User
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import DefaultOrganizationMixin


class ApiKeyPermission(models.TextChoices):
    READ = "read", "Read"
    READ_WRITE = "read_write", "Read/Write"
    FULL_ACCESS = "full_access", "Full Access"

    def allows(self, method: str) -> bool:
        """Whether a key holding this tier may issue the given HTTP method."""
        method = method.upper()
        if self == ApiKeyPermission.FULL_ACCESS:
            return method in {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}
        if self == ApiKeyPermission.READ_WRITE:
            return method in {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH"}
        return method in {"GET", "HEAD", "OPTIONS"}


class PlatformApiKey(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    description = models.TextField(max_length=512)
    # TODO: Store hashed key instead of plaintext. Show plaintext only at
    # create/rotate, then store hash. Retrieve should return masked value.
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=True)
    permission = models.CharField(
        max_length=20,
        choices=ApiKeyPermission.choices,
        default=ApiKeyPermission.READ_WRITE,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="platform_api_keys_created",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    api_user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="platform_api_key_identity",
    )

    class Meta:
        db_table = "platform_api_key"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"],
                name="unique_platform_api_key_name_per_org",
            ),
            models.CheckConstraint(
                check=models.Q(permission__in=ApiKeyPermission.values),
                name="platform_api_key_permission_valid",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization})"
