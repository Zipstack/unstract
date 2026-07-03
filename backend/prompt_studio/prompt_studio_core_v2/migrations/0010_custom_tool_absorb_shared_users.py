import logging

from django.db import migrations

logger = logging.getLogger(__name__)

VIEWER = "viewer"


def backfill_shared_users_as_viewers(apps, schema_editor):
    """Migrate ``shared_users`` M2M entries into VIEWER membership rows.

    Direct user shares become VIEWER-role memberships (UN-2202 Phase 2). A user
    already holding an OWNER row is left as-is (``unique_together``).
    """
    CustomTool = apps.get_model("prompt_studio_core_v2", "CustomTool")
    CustomToolMember = apps.get_model("prompt_studio_core_v2", "CustomToolMember")
    migrated = 0
    for tool in CustomTool.objects.iterator():
        for user_id in tool.shared_users.values_list("id", flat=True):
            _, created = CustomToolMember.objects.get_or_create(
                custom_tool=tool, user_id=user_id, defaults={"role": VIEWER}
            )
            migrated += int(created)
    if migrated:
        logger.info("Backfilled %s shared_users into VIEWER memberships.", migrated)


class Migration(migrations.Migration):
    dependencies = [
        ("prompt_studio_core_v2", "0009_custom_tool_co_owner_membership"),
    ]

    operations = [
        migrations.RunPython(backfill_shared_users_as_viewers, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="customtool",
            name="shared_users",
        ),
    ]
