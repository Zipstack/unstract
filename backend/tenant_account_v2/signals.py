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
    2. Direct membership rows on every shareable resource of that org: all
       VIEWER rows, plus OWNER rows wherever another *live* owner remains
       (:func:`_purge_replaceable_owner_rows`). Closes the co-owner rejoin
       backdoor — a re-invited user (same ``User.id``) would otherwise
       silently regain co-ownership, since ``_is_resource_owner`` grants on
       any surviving OWNER row with no live-membership check. A sole owner's
       OWNER row is kept so the resource is never left ownerless (spec §7.4);
       ``created_by`` (audit) is untouched and admin access is independent
       (``IsOwner`` OR ``_is_organization_admin``).

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

        # Direct access on this org's shareable resources (one polymorphic
        # table, unscoped by ``UserContext`` which is None outside a request).
        # VIEWER rows always go.
        viewer_removed, _ = ResourceMembership.objects.filter(
            user=instance.user,
            organization=instance.organization,
            role=ResourceRole.VIEWER,
        ).delete()

        owner_removed = _purge_replaceable_owner_rows(instance)

        if viewer_removed or owner_removed:
            logger.info(
                "Removed %s VIEWER + %s OWNER memberships for user=%s in org=%s "
                "(kept rows with no other live owner)",
                viewer_removed,
                owner_removed,
                instance.user_id,
                instance.organization_id,
            )


def _purge_replaceable_owner_rows(instance: OrganizationMember) -> int:
    """Delete the departing user's OWNER rows where another LIVE owner remains.

    Sole-owner rows are kept so a resource is never left ownerless (spec §7.4);
    when every live owner departs at once (bulk removal), all their rows are
    kept — the N-user generalisation of the same carve-out. Two subtleties:

    - Liveness: the carve-out deliberately keeps departed users' rows, so a
      surviving OWNER row may belong to an ex-member; counting it as "another
      owner" would purge the last live owner. Only current org members count.
      ``_base_manager`` because ``OrganizationMember``'s default manager is
      org-scoped by ``UserContext`` (None outside a request → an empty live
      set would silently defeat the purge).
    - Locking: ``RemoveOwnerSerializer`` guards the same last-owner invariant,
      so both paths lock the resource's OWNER rows (ordered by pk so
      overlapping scans cannot deadlock) to serialize concurrent removals.
      The departing-user exclusion happens in Python — excluding in SQL would
      let two concurrent departures lock disjoint rows and both purge.
    """
    owner_rows = list(
        ResourceMembership.objects.filter(
            user=instance.user,
            organization=instance.organization,
            role=ResourceRole.OWNER,
        ).values_list("pk", "content_type_id", "object_id")
    )
    if not owner_rows:
        return 0
    # Materialised so every lock is held before the purge decision below.
    peer_rows = list(
        ResourceMembership.objects.select_for_update()
        .filter(
            role=ResourceRole.OWNER,
            object_id__in={oid for _, _, oid in owner_rows},
        )
        .order_by("pk")
        .values_list("user_id", "content_type_id", "object_id")
    )
    live_user_ids = set(
        OrganizationMember._base_manager.filter(
            organization=instance.organization
        ).values_list("user_id", flat=True)
    )
    co_owned = {
        (ct_id, oid)
        for user_id, ct_id, oid in peer_rows
        if user_id != instance.user_id and user_id in live_user_ids
    }
    purge_pks = [pk for pk, ct_id, oid in owner_rows if (ct_id, oid) in co_owned]
    removed, _ = ResourceMembership.objects.filter(pk__in=purge_pks).delete()
    return removed


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
