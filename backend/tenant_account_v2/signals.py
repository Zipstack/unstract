import logging

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models import ManyToManyField
from django.db.models.signals import post_delete
from django.dispatch import receiver
from permissions.roles import ResourceRole

from tenant_account_v2.models import GroupMembership, OrganizationMember
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
    transaction so a mid-loop failure rolls back rather than leaving the user
    partially purged (which would silently re-open the rejoin backdoor).
    """
    with transaction.atomic():
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

        for resource in SHAREABLE_RESOURCES:
            try:
                model = apps.get_model(resource.app_label, resource.model_name)
            except LookupError:
                # App not installed in this deployment (e.g. cloud-only
                # agentic_studio_v1 in pure OSS). Skip cleanly.
                continue
            # Delete via the membership through table, not ``model.objects``:
            # the default manager is org-scoped on ``UserContext`` (None outside
            # an HTTP request), so it would match zero rows in tests /
            # management commands. The through manager is unscoped; scope it
            # explicitly by the resource's own organization.
            try:
                members_field = model._meta.get_field("members")
            except FieldDoesNotExist:
                # A registered model can legitimately lack the membership field
                # during the OSS<->cloud sync window (e.g. AgenticProject
                # before its migration applies). Group memberships were already
                # purged above; skip the direct-share purge here.
                continue
            assert isinstance(members_field, ManyToManyField)
            through = members_field.remote_field.through
            source_fk = members_field.m2m_field_name()  # e.g. "adapter"
            try:
                removed, _ = through.objects.filter(
                    user=instance.user,
                    role=ResourceRole.VIEWER,
                    **{f"{source_fk}__organization": instance.organization},
                ).delete()
            except Exception:
                logger.exception(
                    "Failed purging VIEWER memberships for user=%s on %s.%s "
                    "org=%s; rolling back the whole purge",
                    instance.user_id,
                    resource.app_label,
                    resource.model_name,
                    instance.organization_id,
                )
                raise
            if removed:
                logger.info(
                    "Removed %s VIEWER memberships for user=%s on %s.%s in org=%s",
                    removed,
                    instance.user_id,
                    resource.app_label,
                    resource.model_name,
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
