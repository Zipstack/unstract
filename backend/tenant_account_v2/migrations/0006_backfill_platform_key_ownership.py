"""Re-point service-account OWNER rows to the key's live creator.

Rows written before ``owner_user_for`` existed name the service account, which
every owner surface filters out. Skips a creator who has left the org, matching
the resolver. Idempotent.

The repair itself lives in ``_membership_backfill.repair_platform_key_ownership``
so a cloud-only app -- which this migration can't declare a dependency on --
can import and re-run it after its own absorb-shared-users migration.
"""

from django.db import migrations

from tenant_account_v2.migrations._membership_backfill import (
    repair_platform_key_ownership,
)


def _forward(apps, schema_editor):
    repair_platform_key_ownership(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("tenant_account_v2", "0005_resource_membership"),
        ("platform_api", "0004_alter_platformapikey_organization"),
        # UN-2202's backfills write an OWNER row from ``created_by``, which is
        # the service account on a key-created resource. They must land before
        # this one or their rows are written after the repair and stay
        # ownerless -- ordering that was otherwise alphabetical accident, and
        # already wrong for workflow_v2.
        ("adapter_processor_v2", "0005_absorb_shared_users"),
        ("api_v2", "0005_absorb_shared_users"),
        ("connector_v2", "0007_absorb_shared_users"),
        ("pipeline_v2", "0005_absorb_shared_users"),
        ("prompt_studio_core_v2", "0009_absorb_shared_users"),
        ("workflow_v2", "0022_absorb_shared_users"),
    ]

    # Irreversible in substance: which rows were the service account's is not
    # recoverable afterwards. Reversing is a no-op so the migration can still
    # be unapplied without blocking a rollback.
    operations = [migrations.RunPython(_forward, migrations.RunPython.noop)]
