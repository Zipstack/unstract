import logging

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

logger = logging.getLogger(__name__)

OWNER = "owner"


def backfill_creator_as_owner(apps, schema_editor):
    """Add each adapter's creator as an OWNER membership row.

    ``created_by`` is now audit-only; the creator's access flows through this
    OWNER row. Adapters with a null ``created_by`` (SET_NULL orphans /
    frictionless) are skipped — they have no owner and stay reachable only via
    org-admin / service-account overrides.
    """
    AdapterInstance = apps.get_model("adapter_processor_v2", "AdapterInstance")
    AdapterMember = apps.get_model("adapter_processor_v2", "AdapterMember")
    skipped = 0
    for adapter in AdapterInstance.objects.iterator():
        if not adapter.created_by_id:
            skipped += 1
            continue
        AdapterMember.objects.get_or_create(
            adapter=adapter,
            user_id=adapter.created_by_id,
            defaults={"role": OWNER},
        )
    if skipped:
        logger.warning(
            "Skipped %s adapters with null created_by (no owner backfilled).", skipped
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("adapter_processor_v2", "0004_alter_adapterinstance_organization"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdapterMember",
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
                    "adapter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="adapter_processor_v2.adapterinstance",
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
                "db_table": "adapter_member",
                "unique_together": {("user", "adapter")},
            },
        ),
        migrations.AddField(
            model_name="adapterinstance",
            name="members",
            field=models.ManyToManyField(
                help_text="Users with a role (owner/viewer) on this adapter.",
                related_name="adapters_member_of",
                through="adapter_processor_v2.AdapterMember",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="adaptermember",
            index=models.Index(
                fields=["adapter", "role"], name="adapter_member_role_idx"
            ),
        ),
        migrations.RunPython(backfill_creator_as_owner, migrations.RunPython.noop),
    ]
