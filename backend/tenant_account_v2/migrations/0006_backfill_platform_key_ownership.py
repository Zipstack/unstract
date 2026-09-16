"""Re-point service-account OWNER rows to the key's live creator.

Rows written before ``owner_user_for`` existed name the service account, which
every owner surface filters out. Skips a creator who has left the org, matching
the resolver. Idempotent.
"""

from django.db import migrations
from django.utils import timezone

OWNER = "owner"


def _forward(apps, schema_editor):
    resource_membership_model = apps.get_model("tenant_account_v2", "ResourceMembership")
    organization_member_model = apps.get_model("tenant_account_v2", "OrganizationMember")
    platform_api_key_model = apps.get_model("platform_api", "PlatformApiKey")

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


class Migration(migrations.Migration):
    dependencies = [
        ("tenant_account_v2", "0005_resource_membership"),
        ("platform_api", "0004_alter_platformapikey_organization"),
        # UN-2202's backfills write an OWNER row from ``created_by``, which is
        # the service account on a key-created resource. They must land before
        # this one or their rows are written after the repair and stay
        # ownerless -- ordering that was otherwise alphabetical accident, and
        # already wrong for workflow_v2.
        ("adapter_processor_v2", "0005_absorb_shared_users"),
        ("api_v2", "0005_absorb_shared_users"),
        ("connector_v2", "0007_absorb_shared_users"),
        ("pipeline_v2", "0005_absorb_shared_users"),
        ("prompt_studio_core_v2", "0009_absorb_shared_users"),
        ("workflow_v2", "0022_absorb_shared_users"),
    ]

    # Irreversible in substance: which rows were the service account's is not
    # recoverable afterwards. Reversing is a no-op so the migration can still
    # be unapplied without blocking a rollback.
    operations = [migrations.RunPython(_forward, migrations.RunPython.noop)]
