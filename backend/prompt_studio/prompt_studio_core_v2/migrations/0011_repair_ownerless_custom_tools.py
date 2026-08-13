"""UN-3057: grant an OWNER row to custom tools left ownerless by the clone path.

The Prompt Studio clone helper never created the OWNER ``ResourceMembership``
that UN-2202 made authoritative, so every project cloned after
``0009_absorb_shared_users`` ran has no owner: visible (the clone copies the
parent's ``shared_to_org``) but unmanageable by anyone except an org admin.
The helper is fixed going forward; this repairs the rows already written.

Idempotent and non-destructive — only resources with zero OWNER rows are
touched, so it is safe to re-run and reverses to a no-op.
"""

from django.db import migrations
from tenant_account_v2.migrations._membership_backfill import (
    repair_ownerless_owner_rows,
)

APP_LABEL = "prompt_studio_core_v2"
MODEL_NAME = "CustomTool"


def _forward(apps, schema_editor):
    repair_ownerless_owner_rows(apps, APP_LABEL, MODEL_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("prompt_studio_core_v2", "0010_customtool_custtool_org_modified_idx"),
        ("tenant_account_v2", "0005_resource_membership"),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
    ]
