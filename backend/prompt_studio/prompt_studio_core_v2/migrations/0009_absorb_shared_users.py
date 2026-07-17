"""UN-2202: absorb custom tool creator + shared_users into ResourceMembership.

Backfill runs before ``shared_users`` is removed, so it can still read it.
"""

from django.db import migrations
from tenant_account_v2.migrations._membership_backfill import backfill_memberships

APP_LABEL = "prompt_studio_core_v2"
MODEL_NAME = "CustomTool"


def _forward(apps, schema_editor):
    backfill_memberships(apps, APP_LABEL, MODEL_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("prompt_studio_core_v2", "0008_alter_customtool_organization"),
        ("tenant_account_v2", "0005_resource_membership"),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
        migrations.RemoveField(model_name="customtool", name="shared_users"),
    ]
