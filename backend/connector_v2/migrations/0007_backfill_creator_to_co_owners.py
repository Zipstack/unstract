from django.db import migrations


def backfill_creator_to_co_owners(apps, schema_editor):
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")
    for connector in ConnectorInstance.objects.filter(created_by__isnull=False):
        if not connector.co_owners.filter(id=connector.created_by_id).exists():
            connector.co_owners.add(connector.created_by)


class Migration(migrations.Migration):
    dependencies = [
        ("connector_v2", "0006_connectorinstance_co_owners"),
    ]

    operations = [
        migrations.RunPython(
            backfill_creator_to_co_owners,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
