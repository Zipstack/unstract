from django.db import migrations


def backfill_creator_to_co_owners(apps, schema_editor):
    Workflow = apps.get_model("workflow_v2", "Workflow")
    for workflow in Workflow.objects.filter(created_by__isnull=False):
        if not workflow.co_owners.filter(id=workflow.created_by_id).exists():
            workflow.co_owners.add(workflow.created_by)


class Migration(migrations.Migration):
    dependencies = [
        ("workflow_v2", "0020_workflow_co_owners"),
    ]

    operations = [
        migrations.RunPython(
            backfill_creator_to_co_owners,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
