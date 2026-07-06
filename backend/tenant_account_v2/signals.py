import logging

from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from permissions.roles import ResourceRole

from tenant_account_v2.models import (
    GroupMembership,
    OrganizationMember,
    ResourceMembership,
)
from tenant_account_v2.shareable_resources import SHAREABLE_RESOURCES

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=OrganizationMember)
def cleanup_user_org_access(
    sender: type, instance: OrganizationMember, **kwargs: object
) -> None:
    """Revoke a user's org-scoped access on org membership removal.

    Two cleanups:
    1. Group memberships for that org (group-derived access goes away live
       via ``for_user()``).
    2. Direct VIEWER membership rows on every shareable resource of that org
       — closes the rejoin backdoor where a re-invited user would silently
       regain direct access. OWNER rows are left intact (parity with the old
       ``shared_users``-only purge, where ``created_by`` ownership survived
       re-invite); a departing owner's resources stay admin-manageable.

    Uses a signal (not DB CASCADE) so notification / audit hooks can attach
    here later without a schema change. The whole purge runs in one
    transaction so a mid-step failure rolls back rather than leaving the user
    partially purged (which would silently re-open the rejoin backdoor).
    """
    with transaction.atomic():
        deleted_count, _ = GroupMembership.objects.filter(
            group__organization=instance.organization,
            user=instance.user,
        ).delete()
        if deleted_count:
            logger.info(
                "Removed %s group memberships for user=%s org=%s after "
                "OrganizationMember delete",
                deleted_count,
                instance.user_id,
                instance.organization_id,
            )

        # One polymorphic table + explicit ``organization`` FK — a single
        # query purges direct VIEWER access across every shareable resource,
        # unscoped by ``UserContext`` (None outside an HTTP request).
        removed, _ = ResourceMembership.objects.filter(
            user=instance.user,
            organization=instance.organization,
            role=ResourceRole.VIEWER,
        ).delete()
        if removed:
            logger.info(
                "Removed %s VIEWER memberships for user=%s in org=%s",
                removed,
                instance.user_id,
                instance.organization_id,
            )


def cleanup_resource_group_shares(
    sender: type, instance: object, **kwargs: object
) -> None:
    """Purge ``ResourceGroupShare`` rows when a shareable resource is deleted.

    ``object_id`` is a plain varchar (no FK/CASCADE), so group-share rows would
    otherwise dangle indefinitely after the resource is gone.
    """
    from django.contrib.contenttypes.models import ContentType

    from tenant_account_v2.models import ResourceGroupShare

    # post_delete fires inside the resource-delete transaction; on failure the
    # delete rolls back. Mirror ``cleanup_user_org_access``: name the
    # sender/pk so the rollback is diagnosable, then re-raise.
    try:
        deleted, _ = ResourceGroupShare.objects.filter(
            content_type=ContentType.objects.get_for_model(sender),
            object_id=str(instance.pk),
        ).delete()
    except Exception:
        logger.exception(
            "Failed purging ResourceGroupShare rows after %s(%s) delete; "
            "rolling back the resource deletion",
            sender.__name__,
            instance.pk,
        )
        raise
    if deleted:
        logger.info(
            "Removed %s ResourceGroupShare rows after %s(%s) delete",
            deleted,
            sender.__name__,
            instance.pk,
        )


def _connect_resource_group_share_cleanup() -> None:
    """Wire :func:`cleanup_resource_group_shares` to each installed shareable
    model. Lazy per-model connect so OSS deployments without the cloud agentic
    app skip it cleanly; ``dispatch_uid`` keeps the connect idempotent.
    """
    for resource in SHAREABLE_RESOURCES:
        try:
            model = apps.get_model(resource.app_label, resource.model_name)
        except LookupError:
            continue
        post_delete.connect(
            cleanup_resource_group_shares,
            sender=model,
            dispatch_uid=(
                f"cleanup_resource_group_shares_{resource.app_label}_{resource.model_name}"
            ),
        )


_connect_resource_group_share_cleanup()
