import logging

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

logger = logging.getLogger(__name__)

OWNER = "owner"


def backfill_creator_as_owner(apps, schema_editor):
    """Add each pipeline's creator as an OWNER membership row.

    ``created_by`` is now audit-only; the creator's access flows through this
    OWNER row. Pipelines with a null ``created_by`` are skipped.
    """
    Pipeline = apps.get_model("pipeline_v2", "Pipeline")
    PipelineMember = apps.get_model("pipeline_v2", "PipelineMember")
    skipped = 0
    for pipeline in Pipeline.objects.iterator():
        if not pipeline.created_by_id:
            skipped += 1
            continue
        PipelineMember.objects.get_or_create(
            pipeline=pipeline,
            user_id=pipeline.created_by_id,
            defaults={"role": OWNER},
        )
    if skipped:
        logger.warning(
            "Skipped %s pipelines with null created_by (no owner backfilled).", skipped
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pipeline_v2", "0004_alter_pipeline_organization"),
    ]

    operations = [
        migrations.CreateModel(
            name="PipelineMember",
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
                    "pipeline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="pipeline_v2.pipeline",
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
                "db_table": "pipeline_member",
                "unique_together": {("user", "pipeline")},
            },
        ),
        migrations.AddField(
            model_name="pipeline",
            name="members",
            field=models.ManyToManyField(
                help_text="Users with a role (owner/viewer) on this pipeline.",
                related_name="pipelines_member_of",
                through="pipeline_v2.PipelineMember",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="pipelinemember",
            index=models.Index(
                fields=["pipeline", "role"], name="pipeline_member_role_idx"
            ),
        ),
        migrations.RunPython(backfill_creator_as_owner, migrations.RunPython.noop),
    ]
