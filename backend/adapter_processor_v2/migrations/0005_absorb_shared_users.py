"""UN-2202: absorb adapter creator + shared_users into ResourceMembership.

Backfill runs before ``shared_users`` is removed, so it can still read it.
"""

from django.db import migrations
from tenant_account_v2.migrations._membership_backfill import backfill_memberships

APP_LABEL = "adapter_processor_v2"
MODEL_NAME = "AdapterInstance"


def _forward(apps, schema_editor):
    backfill_memberships(apps, APP_LABEL, MODEL_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("adapter_processor_v2", "0004_alter_adapterinstance_organization"),
        ("tenant_account_v2", "0005_resource_membership"),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
        migrations.RemoveField(model_name="adapterinstance", name="shared_users"),
    ]
