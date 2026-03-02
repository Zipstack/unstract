from django.db import migrations


def backfill_creator_to_co_owners(apps, schema_editor):
    custom_tool_model = apps.get_model("prompt_studio_core_v2", "CustomTool")
    for tool in custom_tool_model.objects.filter(created_by__isnull=False):
        if not tool.co_owners.filter(id=tool.created_by_id).exists():
            tool.co_owners.add(tool.created_by)


class Migration(migrations.Migration):
    dependencies = [
        ("prompt_studio_core_v2", "0007_customtool_co_owners"),
    ]

    operations = [
        migrations.RunPython(
            backfill_creator_to_co_owners,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
