"""Shared backfill for the UN-2202 single-table membership migration.

Lives inside the migrations package with a ``_`` prefix so Django's migration
loader skips it (it only treats non-``_``/``~`` modules as migrations), while
the per-app membership migrations can still import it and stay thin instead of
each carrying its own copy.

Idempotent: ``get_or_create`` is keyed on the unique ``(user, content_type,
object_id)`` triple, so re-runs and the creator-is-also-a-shared-user overlap
are both safe (the existing OWNER row wins over a would-be VIEWER row).
"""

import logging

logger = logging.getLogger(__name__)

OWNER = "owner"
VIEWER = "viewer"


def backfill_memberships(apps, app_label: str, model_name: str) -> None:
    """Absorb a resource's creator + ``shared_users`` into ``ResourceMembership``.

    Creator becomes an OWNER row, each direct ``shared_users`` entry a VIEWER
    row (UN-2202). ``created_by`` is left as audit-only metadata; a null creator
    is skipped (the resource has no owner and stays reachable only via
    org-admin / service-account overrides).
    """
    Resource = apps.get_model(app_label, model_name)
    Membership = apps.get_model("tenant_account_v2", "ResourceMembership")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type = ContentType.objects.get_for_model(Resource)
    owners = viewers = skipped = skipped_org = 0
    for resource in Resource.objects.iterator():
        # A NULL-org resource can't carry tenant-scoped membership rows (the
        # organization FK is NOT NULL) — skip it rather than abort the migration.
        if resource.organization_id is None:
            skipped_org += 1
            continue
        object_id = str(resource.pk)
        if resource.created_by_id:
            _, created = Membership.objects.get_or_create(
                content_type=content_type,
                object_id=object_id,
                user_id=resource.created_by_id,
                defaults={"role": OWNER, "organization_id": resource.organization_id},
            )
            owners += int(created)
        else:
            skipped += 1
        for user_id in resource.shared_users.values_list("id", flat=True):
            _, created = Membership.objects.get_or_create(
                content_type=content_type,
                object_id=object_id,
                user_id=user_id,
                defaults={"role": VIEWER, "organization_id": resource.organization_id},
            )
            viewers += int(created)

    logger.info(
        "%s.%s memberships backfilled: owners=%s viewers=%s "
        "(skipped %s null-creator, %s null-org)",
        app_label,
        model_name,
        owners,
        viewers,
        skipped,
        skipped_org,
    )
