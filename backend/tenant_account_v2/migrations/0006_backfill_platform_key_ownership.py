"""UN-3853: re-point service-account OWNER rows to the key's creator.

Rows written before ``owner_user_for`` existed name the key's service account.
Every owner surface filters those out, so the resource shows no owner and only
an org admin can manage it. This hands each one to the same successor the
resolver picks, under the same membership rule -- a creator who has left the
org is skipped, since granting them a fresh OWNER row would reopen the rejoin
backdoor ``cleanup_user_org_access`` exists to close.

Idempotent: a second run finds no service-account OWNER rows left to move.
"""

from django.db import migrations

OWNER = "owner"


def _forward(apps, schema_editor):
    ResourceMembership = apps.get_model("tenant_account_v2", "ResourceMembership")
    OrganizationMember = apps.get_model("tenant_account_v2", "OrganizationMember")
    PlatformApiKey = apps.get_model("platform_api", "PlatformApiKey")

    # Successor per service account. Keyed off the key rows rather than
    # ``is_service_account`` so only accounts that actually back a key move.
    successor: dict[int, int] = {}
    for key in PlatformApiKey.objects.exclude(api_user_id=None).exclude(
        created_by_id=None
    ):
        if OrganizationMember.objects.filter(
            user_id=key.created_by_id, organization_id=key.organization_id
        ).exists():
            successor[key.api_user_id] = key.created_by_id

    if not successor:
        return

    rows = ResourceMembership.objects.filter(role=OWNER, user_id__in=successor.keys())
    for row in rows.iterator():
        new_user_id = successor[row.user_id]
        clash = ResourceMembership.objects.filter(
            user_id=new_user_id,
            content_type_id=row.content_type_id,
            object_id=row.object_id,
        ).first()
        if clash is None:
            row.user_id = new_user_id
            row.save(update_fields=["user"])
            continue
        # The creator already holds a row on this resource. Keep the stronger
        # role and drop the service account's, so (user, content_type,
        # object_id) is never violated -- mirrors _transfer_membership_rows.
        if clash.role != OWNER:
            clash.role = OWNER
            clash.save(update_fields=["role"])
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
