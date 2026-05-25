import uuid

from account_v2.models import User
from api_v2.models import APIDeployment
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import DefaultOrganizationMixin


class GlobalApiDeploymentKey(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    description = models.TextField(max_length=512)
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=True)
    allow_all_deployments = models.BooleanField(
        default=False,
        db_comment="If True, this key can authenticate any API deployment in the org",
    )
    api_deployments = models.ManyToManyField(
        APIDeployment,
        blank=True,
        related_name="global_api_deployment_keys",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="global_api_deployment_keys_created",
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )

    class Meta:
        db_table = "global_api_deployment_key"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"],
                name="unique_global_api_deployment_key_name_per_org",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization})"

    def has_access_to_deployment(self, api_deployment):
        """Check if this key can authenticate the given API deployment."""
        if not self.is_active:
            return False
        if self.organization_id != api_deployment.organization_id:
            return False
        if self.allow_all_deployments:
            return True
        return self.api_deployments.filter(id=api_deployment.id).exists()
