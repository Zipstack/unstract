from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account_v2", "0005_alter_platformkey_organization"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="restrict_llm_adapter_creation",
            field=models.BooleanField(
                db_comment=(
                    "Controlled mode: when True, only organization admins may "
                    "create LLM adapters in this org. Default False preserves "
                    "open creation."
                ),
                default=False,
            ),
        ),
    ]
