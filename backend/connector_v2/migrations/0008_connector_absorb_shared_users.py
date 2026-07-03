import logging

from django.db import migrations

logger = logging.getLogger(__name__)

VIEWER = "viewer"


def backfill_shared_users_as_viewers(apps, schema_editor):
    """Migrate ``shared_users`` M2M entries into VIEWER membership rows.

    Direct user shares become VIEWER-role memberships (UN-2202 Phase 2). A user
    already holding an OWNER row is left as-is (``unique_together``).
    """
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")
    ConnectorMember = apps.get_model("connector_v2", "ConnectorMember")
    migrated = 0
    for connector in ConnectorInstance.objects.iterator():
        for user_id in connector.shared_users.values_list("id", flat=True):
            _, created = ConnectorMember.objects.get_or_create(
                connector=connector, user_id=user_id, defaults={"role": VIEWER}
            )
            migrated += int(created)
    if migrated:
        logger.info("Backfilled %s shared_users into VIEWER memberships.", migrated)


class Migration(migrations.Migration):
    dependencies = [
        ("connector_v2", "0007_connector_co_owner_membership"),
    ]

    operations = [
        migrations.RunPython(backfill_shared_users_as_viewers, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="connectorinstance",
            name="shared_users",
        ),
    ]
