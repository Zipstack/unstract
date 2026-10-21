from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account_v2", "0007_organization_restrict_connector_creation"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="profile_display_name",
            field=models.CharField(
                blank=True,
                db_comment=(
                    "Name the user set on their profile; empty means the identity "
                    "provider's name is shown"
                ),
                default="",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="language",
            field=models.CharField(
                db_comment="Preferred UI language (BCP 47)",
                default="en-US",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="profile_photo_updated_at",
            field=models.DateTimeField(
                blank=True,
                db_comment="When the profile photo was stored; null when there is none",
                null=True,
            ),
        ),
    ]
