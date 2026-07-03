import logging

from django.db import migrations

logger = logging.getLogger(__name__)

VIEWER = "viewer"


def backfill_shared_users_as_viewers(apps, schema_editor):
    """Migrate ``shared_users`` M2M entries into VIEWER membership rows.

    Direct user shares become VIEWER-role memberships (UN-2202 Phase 2). A user
    already holding an OWNER row is left as-is (``unique_together``).
    """
    Pipeline = apps.get_model("pipeline_v2", "Pipeline")
    PipelineMember = apps.get_model("pipeline_v2", "PipelineMember")
    migrated = 0
    for pipeline in Pipeline.objects.iterator():
        for user_id in pipeline.shared_users.values_list("id", flat=True):
            _, created = PipelineMember.objects.get_or_create(
                pipeline=pipeline, user_id=user_id, defaults={"role": VIEWER}
            )
            migrated += int(created)
    if migrated:
        logger.info("Backfilled %s shared_users into VIEWER memberships.", migrated)


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_v2", "0005_pipeline_co_owner_membership"),
    ]

    operations = [
        migrations.RunPython(backfill_shared_users_as_viewers, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="pipeline",
            name="shared_users",
        ),
    ]
