# Generated by Django 4.2.1 on 2024-07-14 08:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prompt_studio_core", "0013_customtool_enable_highlight"),
    ]

    operations = [
        migrations.AddField(
            model_name="customtool",
            name="tag_id",
            field=models.TextField(
                blank=True,
                db_comment="Currently checked-in tag id",
                default=None,
                null=True,
            ),
        ),
    ]