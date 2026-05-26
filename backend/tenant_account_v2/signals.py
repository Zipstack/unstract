import logging

from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from tenant_account_v2.models import GroupMembership, OrganizationMember

logger = logging.getLogger(__name__)

# (app_label, model_name) for every shareable resource. Lazy-loaded via
# ``apps.get_model`` so signals can fire before cross-app imports resolve, and
# so OSS-only deployments without the cloud agentic app skip cleanly.
_SHAREABLE_MODELS: tuple[tuple[str, str], ...] = (
    ("workflow_v2", "Workflow"),
    ("pipeline_v2", "Pipeline"),
    ("api_v2", "APIDeployment"),
    ("connector_v2", "ConnectorInstance"),
    ("adapter_processor_v2", "AdapterInstance"),
    ("prompt_studio_core_v2", "CustomTool"),
    ("agentic_studio_v1", "AgenticProject"),  # cloud-only
)


@receiver(post_delete, sender=OrganizationMember)
def cleanup_user_org_access(
    sender: type, instance: OrganizationMember, **kwargs: object
) -> None:
    """Revoke a user's org-scoped access on org membership removal.

    Two cleanups:
    1. Group memberships for that org (group-derived access goes away live
       via ``for_user()``).
    2. Direct ``shared_users`` M2M entries on every shareable resource of
       that org — closes the rejoin backdoor where a re-invited user would
       silently regain direct access.

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

        for app_label, model_name in _SHAREABLE_MODELS:
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                # App not installed in this deployment (e.g. cloud-only
                # agentic_studio_v1 in pure OSS). Skip cleanly.
                continue
            try:
                resources = model.objects.filter(
                    organization=instance.organization,
                    shared_users=instance.user,
                )
                removed = 0
                for resource in resources:
                    resource.shared_users.remove(instance.user)
                    removed += 1
            except Exception:
                logger.exception(
                    "Failed purging shared_users for user=%s on %s.%s org=%s; "
                    "rolling back the whole purge",
                    instance.user_id,
                    app_label,
                    model_name,
                    instance.organization_id,
                )
                raise
            if removed:
                logger.info(
                    "Removed user=%s from shared_users on %s %s.%s rows in org=%s",
                    instance.user_id,
                    removed,
                    app_label,
                    model_name,
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

    deleted, _ = ResourceGroupShare.objects.filter(
        content_type=ContentType.objects.get_for_model(sender),
        object_id=str(instance.pk),
    ).delete()
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
    for app_label, model_name in _SHAREABLE_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        post_delete.connect(
            cleanup_resource_group_shares,
            sender=model,
            dispatch_uid=f"cleanup_resource_group_shares_{app_label}_{model_name}",
        )


_connect_resource_group_share_cleanup()
