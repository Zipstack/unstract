"""Grant ``created_by`` an OWNER row on custom tools that have no owner.

Only resources with zero OWNER rows are touched, so it is safe to re-run and
reverses to a no-op. Owner rows that name a platform key's service account
are then re-pointed to the key's creator.
"""

from django.db import migrations
from tenant_account_v2.migrations._membership_backfill import (
    repair_ownerless_owner_rows,
    repair_platform_key_ownership,
)

APP_LABEL = "prompt_studio_core_v2"
MODEL_NAME = "CustomTool"


def _forward(apps, schema_editor):
    repair_ownerless_owner_rows(apps, APP_LABEL, MODEL_NAME)
    repair_platform_key_ownership(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("prompt_studio_core_v2", "0010_customtool_custtool_org_modified_idx"),
        ("tenant_account_v2", "0005_resource_membership"),
        ("platform_api", "0004_alter_platformapikey_organization"),
        ("tenant_account_v2", "0005_resource_membership"),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
    ]
