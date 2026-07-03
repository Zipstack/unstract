import logging

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

logger = logging.getLogger(__name__)

OWNER = "owner"


def backfill_creator_as_owner(apps, schema_editor):
    """Add each workflow's creator as an OWNER membership row.

    ``created_by`` is now audit-only; the creator's access flows through this
    OWNER row. Workflows with a null ``created_by`` are skipped.
    """
    Workflow = apps.get_model("workflow_v2", "Workflow")
    WorkflowMember = apps.get_model("workflow_v2", "WorkflowMember")
    skipped = 0
    for workflow in Workflow.objects.iterator():
        if not workflow.created_by_id:
            skipped += 1
            continue
        WorkflowMember.objects.get_or_create(
            workflow=workflow,
            user_id=workflow.created_by_id,
            defaults={"role": OWNER},
        )
    if skipped:
        logger.warning(
            "Skipped %s workflows with null created_by (no owner backfilled).", skipped
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("workflow_v2", "0021_alter_workflow_organization"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowMember",
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
                    "workflow",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="workflow_v2.workflow",
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
                "db_table": "workflow_member",
                "unique_together": {("user", "workflow")},
            },
        ),
        migrations.AddField(
            model_name="workflow",
            name="members",
            field=models.ManyToManyField(
                help_text="Users with a role (owner/viewer) on this workflow.",
                related_name="workflows_member_of",
                through="workflow_v2.WorkflowMember",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="workflowmember",
            index=models.Index(
                fields=["workflow", "role"], name="workflow_member_role_idx"
            ),
        ),
        migrations.RunPython(backfill_creator_as_owner, migrations.RunPython.noop),
    ]
