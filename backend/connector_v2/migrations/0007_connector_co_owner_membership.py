import logging

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

logger = logging.getLogger(__name__)

OWNER = "owner"


def backfill_creator_as_owner(apps, schema_editor):
    """Add each connector's creator as an OWNER membership row.

    ``created_by`` is now audit-only; the creator's access flows through this
    OWNER row. Connectors with a null ``created_by`` are skipped.
    """
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")
    ConnectorMember = apps.get_model("connector_v2", "ConnectorMember")
    skipped = 0
    for connector in ConnectorInstance.objects.iterator():
        if not connector.created_by_id:
            skipped += 1
            continue
        ConnectorMember.objects.get_or_create(
            connector=connector,
            user_id=connector.created_by_id,
            defaults={"role": OWNER},
        )
    if skipped:
        logger.warning(
            "Skipped %s connectors with null created_by (no owner backfilled).", skipped
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("connector_v2", "0006_alter_connectorinstance_organization"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConnectorMember",
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
                    "connector",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="connector_v2.connectorinstance",
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
                "db_table": "connector_member",
                "unique_together": {("user", "connector")},
            },
        ),
        migrations.AddField(
            model_name="connectorinstance",
            name="members",
            field=models.ManyToManyField(
                help_text="Users with a role (owner/viewer) on this connector.",
                related_name="connectors_member_of",
                through="connector_v2.ConnectorMember",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="connectormember",
            index=models.Index(
                fields=["connector", "role"], name="connector_member_role_idx"
            ),
        ),
        migrations.RunPython(backfill_creator_as_owner, migrations.RunPython.noop),
    ]
