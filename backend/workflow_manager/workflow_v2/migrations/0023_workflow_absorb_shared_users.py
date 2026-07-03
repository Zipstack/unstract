import logging

from django.db import migrations

logger = logging.getLogger(__name__)

VIEWER = "viewer"


def backfill_shared_users_as_viewers(apps, schema_editor):
    """Migrate ``shared_users`` M2M entries into VIEWER membership rows.

    Direct user shares become VIEWER-role memberships (UN-2202 Phase 2). A user
    already holding an OWNER row is left as-is (``unique_together``).
    """
    Workflow = apps.get_model("workflow_v2", "Workflow")
    WorkflowMember = apps.get_model("workflow_v2", "WorkflowMember")
    migrated = 0
    for workflow in Workflow.objects.iterator():
        for user_id in workflow.shared_users.values_list("id", flat=True):
            _, created = WorkflowMember.objects.get_or_create(
                workflow=workflow, user_id=user_id, defaults={"role": VIEWER}
            )
            migrated += int(created)
    if migrated:
        logger.info("Backfilled %s shared_users into VIEWER memberships.", migrated)


class Migration(migrations.Migration):
    dependencies = [
        ("workflow_v2", "0022_workflow_co_owner_membership"),
    ]

    operations = [
        migrations.RunPython(backfill_shared_users_as_viewers, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="workflow",
            name="shared_users",
        ),
    ]
