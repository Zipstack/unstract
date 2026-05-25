from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_api", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="platformapikey",
            name="permission",
            field=models.CharField(
                choices=[
                    ("read", "Read"),
                    ("read_write", "Read/Write"),
                    ("full_access", "Full Access"),
                ],
                default="read_write",
                max_length=20,
            ),
        ),
    ]
