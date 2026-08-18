"""UN-2202: absorb connector creator + shared_users into ResourceMembership.

Backfill runs before ``shared_users`` is removed, so it can still read it.
"""

from django.db import migrations
from tenant_account_v2.migrations._membership_backfill import backfill_memberships

APP_LABEL = "connector_v2"
MODEL_NAME = "ConnectorInstance"


def _forward(apps, schema_editor):
    backfill_memberships(apps, APP_LABEL, MODEL_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("connector_v2", "0006_alter_connectorinstance_organization"),
        ("tenant_account_v2", "0005_resource_membership"),
    ]

    operations = [
        migrations.RunPython(_forward, migrations.RunPython.noop),
        migrations.RemoveField(model_name="connectorinstance", name="shared_users"),
    ]
