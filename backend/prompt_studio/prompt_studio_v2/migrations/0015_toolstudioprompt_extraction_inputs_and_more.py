from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("prompt_studio_v2", "0014_alter_toolstudioprompt_enforce_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="toolstudioprompt",
            name="extraction_inputs",
            field=models.TextField(
                choices=[
                    ("text", "Text only (default)"),
                    ("image", "Page image only"),
                    ("both", "Text and page image"),
                ],
                db_comment="What inputs to send to the LLM: text, image, or both",
                default="text",
            ),
        ),
        migrations.AddField(
            model_name="toolstudioprompt",
            name="source_of_truth",
            field=models.TextField(
                choices=[
                    ("text", "Text is source of truth"),
                    ("image", "Image is source of truth"),
                ],
                db_comment="Which input is source of truth "
                "(only meaningful when extraction_inputs=both)",
                default="text",
            ),
        ),
    ]
