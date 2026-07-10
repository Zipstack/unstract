from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account_v2", "0006_organization_restrict_llm_adapter_creation"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="restrict_connector_creation",
            field=models.BooleanField(
                db_comment=(
                    "Controlled mode: when True, only organization admins may "
                    "create connectors in this org. Default False preserves "
                    "open creation."
                ),
                default=False,
            ),
        ),
    ]
