import uuid

from account_v2.models import User
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import DefaultOrganizationMixin


class PlatformApiKey(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    description = models.TextField(max_length=512)
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=True)
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
        ]

    def __str__(self):
        return f"{self.name} ({self.organization})"
