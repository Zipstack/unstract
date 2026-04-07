# Generated for agentic table enforce type

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "prompt_studio_v2",
            "0013_toolstudioprompt_enable_postprocessing_webhook_and_more",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="toolstudioprompt",
            name="enforce_type",
            field=models.TextField(
                blank=True,
                choices=[
                    ("text", "Response sent as Text"),
                    ("number", "Response sent as number"),
                    ("email", "Response sent as email"),
                    ("date", "Response sent as date"),
                    ("boolean", "Response sent as boolean"),
                    ("json", "Response sent as json"),
                    (
                        "line-item",
                        "Response sent as line-item which is large a JSON output. If extraction stopped due to token limitation, we try to continue extraction from where it stopped",
                    ),
                    ("table", "Response sent as json"),
                    (
                        "agentic_table",
                        "Response sent as agentic table extraction",
                    ),
                ],
                db_comment="Field to store the type in             which the response to be returned.",
                default="text",
            ),
        ),
    ]
