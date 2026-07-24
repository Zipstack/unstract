import uuid

from account_v2.models import User
from api_v2.models import APIDeployment
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import DefaultOrganizationMixin


class GlobalApiDeploymentKey(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    # CharField (not TextField) so the 512 cap is a real varchar(512) DB
    # invariant, not just a Python-layer serializer validator.
    description = models.CharField(max_length=512)
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

    def has_access_to_deployment(self, api_deployment: APIDeployment) -> bool:
        """Check if this key can authenticate the given API deployment."""
        if not self.is_active:
            return False
        # Load-bearing, not defensive: validate_global_api_deployment_key looks
        # the key up by ``key`` + ``is_active`` with NO org filter, so this is
        # the only thing preventing a key from authenticating another org's
        # deployment.
        if self.organization_id != api_deployment.organization_id:
            return False
        # ``allow_all_deployments`` deliberately wins over ``api_deployments``:
        # the pair is a mode switch, not a union. The coherent pair can't be
        # enforced structurally (a CheckConstraint can't span an M2M, and
        # ``clean()`` runs before M2M rows exist), so the serializers own the
        # invariant — see ``_GlobalApiDeploymentKeyWriteSerializer`` subclasses,
        # which reject/clear a list whenever allow-all is set.
        if self.allow_all_deployments:
            return True
        return self.api_deployments.filter(id=api_deployment.id).exists()
