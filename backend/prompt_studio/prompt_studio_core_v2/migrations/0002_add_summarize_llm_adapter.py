# Generated manually for UN-2239: Add summarize_llm_adapter field

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("adapter_processor_v2", "0001_initial"),
        ("prompt_studio_core_v2", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customtool",
            name="summarize_llm_adapter",
            field=models.ForeignKey(
                blank=True,
                db_comment="Field to store the LLM adapter for summarization",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="custom_tools_summarize_llm",
                to="adapter_processor_v2.adapterinstance",
            ),
        ),
    ]
