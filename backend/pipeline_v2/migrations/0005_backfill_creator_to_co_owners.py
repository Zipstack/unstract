from django.db import migrations


def backfill_creator_to_co_owners(apps, schema_editor):
    pipeline_model = apps.get_model("pipeline_v2", "Pipeline")
    for pipeline in pipeline_model.objects.filter(created_by__isnull=False):
        if not pipeline.co_owners.filter(id=pipeline.created_by_id).exists():
            pipeline.co_owners.add(pipeline.created_by)


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_v2", "0004_pipeline_co_owners"),
    ]

    operations = [
        migrations.RunPython(
            backfill_creator_to_co_owners,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
