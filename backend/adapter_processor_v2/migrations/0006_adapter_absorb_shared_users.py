import logging

from django.db import migrations

logger = logging.getLogger(__name__)

VIEWER = "viewer"


def backfill_shared_users_as_viewers(apps, schema_editor):
    """Migrate ``shared_users`` M2M entries into VIEWER membership rows.

    Direct user shares become VIEWER-role memberships (UN-2202 Phase 2). A user
    already holding an OWNER row is left as-is — ``unique_together(user,
    adapter)`` forbids a second row and ownership already grants access.
    """
    AdapterInstance = apps.get_model("adapter_processor_v2", "AdapterInstance")
    AdapterMember = apps.get_model("adapter_processor_v2", "AdapterMember")
    migrated = 0
    for adapter in AdapterInstance.objects.iterator():
        for user_id in adapter.shared_users.values_list("id", flat=True):
            _, created = AdapterMember.objects.get_or_create(
                adapter=adapter, user_id=user_id, defaults={"role": VIEWER}
            )
            migrated += int(created)
    if migrated:
        logger.info("Backfilled %s shared_users into VIEWER memberships.", migrated)


class Migration(migrations.Migration):
    dependencies = [
        ("adapter_processor_v2", "0005_adapter_co_owner_membership"),
    ]

    operations = [
        migrations.RunPython(backfill_shared_users_as_viewers, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="adapterinstance",
            name="shared_users",
        ),
    ]
