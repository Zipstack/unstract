import logging

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

logger = logging.getLogger(__name__)

OWNER = "owner"


def backfill_creator_as_owner(apps, schema_editor):
    """Add each custom tool's creator as an OWNER membership row.

    ``created_by`` is now audit-only; the creator's access flows through this
    OWNER row. Tools with a null ``created_by`` are skipped.
    """
    CustomTool = apps.get_model("prompt_studio_core_v2", "CustomTool")
    CustomToolMember = apps.get_model("prompt_studio_core_v2", "CustomToolMember")
    skipped = 0
    for tool in CustomTool.objects.iterator():
        if not tool.created_by_id:
            skipped += 1
            continue
        CustomToolMember.objects.get_or_create(
            custom_tool=tool,
            user_id=tool.created_by_id,
            defaults={"role": OWNER},
        )
    if skipped:
        logger.warning(
            "Skipped %s custom tools with null created_by (no owner backfilled).",
            skipped,
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("prompt_studio_core_v2", "0008_alter_customtool_organization"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomToolMember",
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
                    "custom_tool",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="prompt_studio_core_v2.customtool",
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
                "db_table": "custom_tool_member",
                "unique_together": {("user", "custom_tool")},
            },
        ),
        migrations.AddField(
            model_name="customtool",
            name="members",
            field=models.ManyToManyField(
                help_text="Users with a role (owner/viewer) on this custom tool.",
                related_name="custom_tools_member_of",
                through="prompt_studio_core_v2.CustomToolMember",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="customtoolmember",
            index=models.Index(
                fields=["custom_tool", "role"], name="custom_tool_member_role_idx"
            ),
        ),
        migrations.RunPython(backfill_creator_as_owner, migrations.RunPython.noop),
    ]
