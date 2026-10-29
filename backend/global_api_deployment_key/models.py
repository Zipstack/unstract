import logging
import uuid

from account_v2.models import User
from api_v2.models import APIDeployment
from django.db import models
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import DefaultOrganizationMixin

logger = logging.getLogger(__name__)


def deployments_keyable_by(user):
    """API deployments a global key ``user`` creates may cover (UN-4399):
    every one for an org admin, otherwise the ones they own (creator or
    co-owner) -- the rule for minting a deployment's own key
    (``IsParentDeploymentOwner``). An empty queryset for anyone outside the
    organisation.
    """
    # Lazy: tenant_account_v2 imports account_v2, which imports this app.
    from permissions.roles import ResourceRole
    from tenant_account_v2.models import OrganizationMember
    from tenant_account_v2.organization_member_service import (
        OrganizationMemberService,
    )
    from tenant_account_v2.sharing_helpers import resources_visible_via_memberships

    if user is None or not OrganizationMember.objects.filter(user=user).exists():
        return APIDeployment.objects.none()
    if OrganizationMemberService.is_user_organization_admin(user):
        return APIDeployment.objects.all()
    return APIDeployment.objects.filter(
        pk__in=resources_visible_via_memberships(
            APIDeployment, user, role=ResourceRole.OWNER
        )
    )


class GlobalApiDeploymentKey(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    # CharField (not TextField) so the 512 cap is a real varchar(512) DB
    # invariant, not just a Python-layer serializer validator.
    description = models.CharField(max_length=512)
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_comment="Key is rejected from this time on. Null: never expires.",
    )
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
    created_by_member = models.BooleanField(
        default=False,
        db_comment=(
            "True if a non-admin created this key (UN-4399): it then works only "
            "within the deployments its creator may key (deployments_keyable_by)"
        ),
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
        if self.created_by_member and not self._creator_can_access(api_deployment):
            return False
        if self.allow_all_deployments:
            return True
        return self.api_deployments.filter(id=api_deployment.id).exists()

    def _creator_can_access(self, api_deployment: APIDeployment) -> bool:
        """A member's key works only within ``deployments_keyable_by`` its
        creator (UN-4399), so its deployments' other owners never have to find
        and revoke it.
        """
        # Lazy: tenant_account_v2 imports account_v2, which imports this app.
        from tenant_account_v2.models import OrganizationMember

        creator = self.created_by
        if creator is None:
            reason = "its creator was deleted"
        # Both lookups use the organisation the request resolved, which
        # has_access_to_deployment has already matched to this key's.
        elif not OrganizationMember.objects.filter(user=creator).exists():
            reason = "its creator left the organization"
        elif not deployments_keyable_by(creator).filter(pk=api_deployment.pk).exists():
            reason = "its creator does not own the deployment"
        else:
            return True
        logger.warning(
            "Global API key %s refused for deployment %s: %s (creator %s).",
            self.id,
            api_deployment.id,
            reason,
            self.created_by_id,
        )
        return False
