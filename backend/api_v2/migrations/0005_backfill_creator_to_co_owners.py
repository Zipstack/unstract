from django.db import migrations


def backfill_creator_to_co_owners(apps, schema_editor):
    api_deployment_model = apps.get_model("api_v2", "APIDeployment")
    for deployment in api_deployment_model.objects.filter(created_by__isnull=False):
        if not deployment.co_owners.filter(id=deployment.created_by_id).exists():
            deployment.co_owners.add(deployment.created_by)


class Migration(migrations.Migration):
    dependencies = [
        ("api_v2", "0004_apideployment_co_owners"),
    ]

    operations = [
        migrations.RunPython(
            backfill_creator_to_co_owners,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
