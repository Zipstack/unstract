"""Shared backfills for the UN-2202 single-table membership migration.

Lives inside the migrations package with a ``_`` prefix so Django's migration
loader skips it (it only treats non-``_``/``~`` modules as migrations), while
the per-app membership migrations -- OSS and cloud alike -- can still import
it and stay thin instead of each carrying its own copy.

Idempotent: ``get_or_create`` is keyed on the unique ``(user, content_type,
object_id)`` triple, so re-runs and the creator-is-also-a-shared-user overlap
are both safe (the existing OWNER row wins over a would-be VIEWER row).
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

OWNER = "owner"
VIEWER = "viewer"


def backfill_memberships(apps, app_label: str, model_name: str) -> None:
    """Absorb a resource's creator + ``shared_users`` into ``ResourceMembership``.

    Creator becomes an OWNER row, each direct ``shared_users`` entry a VIEWER
    row (UN-2202). ``created_by`` is left as audit-only metadata; a null creator
    gets no OWNER row (its ``shared_users`` still become VIEWER rows, so
    viewer/org/group access is unaffected) — the resource simply has no owner.
    """
    Resource = apps.get_model(app_label, model_name)  # NOSONAR
    Membership = apps.get_model("tenant_account_v2", "ResourceMembership")  # NOSONAR
    ContentType = apps.get_model("contenttypes", "ContentType")  # NOSONAR

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


def repair_platform_key_ownership(apps) -> None:
    """Re-point service-account OWNER rows to the key's live creator.

    Rows written before ``owner_user_for`` existed name the service account,
    which every owner surface filters out. Skips a creator who has left the
    org, matching the resolver. Safe to re-run: a resource type whose OWNER
    rows are written by a migration that lands after this one (cloud-only
    apps this module's app can't declare a dependency on) needs this called
    again from a migration that depends on both.
    """
    resource_membership_model = apps.get_model(
        "tenant_account_v2", "ResourceMembership"
    )  # NOSONAR
    organization_member_model = apps.get_model(
        "tenant_account_v2", "OrganizationMember"
    )  # NOSONAR
    platform_api_key_model = apps.get_model("platform_api", "PlatformApiKey")  # NOSONAR

    # Keyed off key rows so only accounts actually backing a key move.
    successor: dict[int, int] = {}
    for key in platform_api_key_model.objects.exclude(api_user_id=None).exclude(
        created_by_id=None
    ):
        if organization_member_model.objects.filter(
            user_id=key.created_by_id, organization_id=key.organization_id
        ).exists():
            successor[key.api_user_id] = key.created_by_id

    if not successor:
        return

    rows = resource_membership_model.objects.filter(
        role=OWNER, user_id__in=successor.keys()
    )
    for row in rows.iterator():
        new_user_id = successor[row.user_id]
        clash = resource_membership_model.objects.filter(
            user_id=new_user_id,
            content_type_id=row.content_type_id,
            object_id=row.object_id,
        ).first()
        if clash is None:
            row.user_id = new_user_id
            # Historical models skip BaseModel.save's modified_at injection.
            row.modified_at = timezone.now()
            row.save(update_fields=["user", "modified_at"])
            continue
        # Creator already holds a row here: keep the stronger role, drop the
        # service account's, so the uniqueness constraint holds.
        if clash.role != OWNER:
            clash.role = OWNER
            clash.modified_at = timezone.now()
            clash.save(update_fields=["role", "modified_at"])
        row.delete()
