import logging

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

logger = logging.getLogger(__name__)

OWNER = "owner"


def backfill_creator_as_owner(apps, schema_editor):
    """Add each API deployment's creator as an OWNER membership row.

    ``created_by`` is now audit-only; the creator's access flows through this
    OWNER row. Deployments with a null ``created_by`` are skipped.
    """
    APIDeployment = apps.get_model("api_v2", "APIDeployment")
    APIDeploymentMember = apps.get_model("api_v2", "APIDeploymentMember")
    skipped = 0
    for dep in APIDeployment.objects.iterator():
        if not dep.created_by_id:
            skipped += 1
            continue
        APIDeploymentMember.objects.get_or_create(
            api_deployment=dep,
            user_id=dep.created_by_id,
            defaults={"role": OWNER},
        )
    if skipped:
        logger.warning(
            "Skipped %s API deployments with null created_by (no owner backfilled).",
            skipped,
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api_v2", "0004_alter_apideployment_organization_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="APIDeploymentMember",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[("owner", "Owner"), ("viewer", "Viewer")],
                        default="viewer",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "api_deployment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="api_v2.apideployment",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "api_deployment_member",
                "unique_together": {("user", "api_deployment")},
            },
        ),
        migrations.AddField(
            model_name="apideployment",
            name="members",
            field=models.ManyToManyField(
                help_text="Users with a role (owner/viewer) on this API deployment.",
                related_name="api_deployments_member_of",
                through="api_v2.APIDeploymentMember",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="apideploymentmember",
            index=models.Index(
                fields=["api_deployment", "role"], name="apidep_member_role_idx"
            ),
        ),
        migrations.RunPython(backfill_creator_as_owner, migrations.RunPython.noop),
    ]
