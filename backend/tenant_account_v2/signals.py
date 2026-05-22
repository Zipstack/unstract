import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from tenant_account_v2.models import GroupMembership, OrganizationMember

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=OrganizationMember)
def remove_user_from_org_groups(
    sender: type, instance: OrganizationMember, **kwargs: object
) -> None:
    """Cascade group membership removal when a user leaves an organization.

    Uses a signal (not DB CASCADE) so notification / audit hooks can attach
    here later without a schema change.
    """
    deleted_count, _ = GroupMembership.objects.filter(
        group__organization=instance.organization,
        user=instance.user,
    ).delete()
    if deleted_count:
        logger.info(
            "Removed %s group memberships for user=%s org=%s after OrganizationMember delete",
            deleted_count,
            instance.user_id,
            instance.organization_id,
        )
    # TODO: notify affected resource owners of access change (Phase 2)
