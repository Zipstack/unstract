from django.db import migrations


def backfill_creator_to_co_owners(apps, schema_editor):
    AdapterInstance = apps.get_model("adapter_processor_v2", "AdapterInstance")
    for adapter in AdapterInstance.objects.filter(created_by__isnull=False):
        if not adapter.co_owners.filter(id=adapter.created_by_id).exists():
            adapter.co_owners.add(adapter.created_by)


class Migration(migrations.Migration):
    dependencies = [
        ("adapter_processor_v2", "0004_adapterinstance_co_owners"),
    ]

    operations = [
        migrations.RunPython(
            backfill_creator_to_co_owners,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
