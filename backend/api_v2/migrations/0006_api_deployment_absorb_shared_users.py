import logging

from django.db import migrations

logger = logging.getLogger(__name__)

VIEWER = "viewer"


def backfill_shared_users_as_viewers(apps, schema_editor):
    """Migrate ``shared_users`` M2M entries into VIEWER membership rows.

    Direct user shares become VIEWER-role memberships (UN-2202 Phase 2). A user
    already holding an OWNER row is left as-is (``unique_together``).
    """
    APIDeployment = apps.get_model("api_v2", "APIDeployment")
    APIDeploymentMember = apps.get_model("api_v2", "APIDeploymentMember")
    migrated = 0
    for deployment in APIDeployment.objects.iterator():
        for user_id in deployment.shared_users.values_list("id", flat=True):
            _, created = APIDeploymentMember.objects.get_or_create(
                api_deployment=deployment, user_id=user_id, defaults={"role": VIEWER}
            )
            migrated += int(created)
    if migrated:
        logger.info("Backfilled %s shared_users into VIEWER memberships.", migrated)


class Migration(migrations.Migration):
    dependencies = [
        ("api_v2", "0005_api_deployment_co_owner_membership"),
    ]

    operations = [
        migrations.RunPython(backfill_shared_users_as_viewers, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="apideployment",
            name="shared_users",
        ),
    ]
