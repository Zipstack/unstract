from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account_v2", "0009_user_product_preference"),
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
        # Database defaults too, so pods still on the old code can create users
        # while a deploy rolls out.
        migrations.RunSQL(
            sql=[
                """ALTER TABLE "user" ALTER COLUMN "profile_display_name" SET DEFAULT ''""",
                """ALTER TABLE "user" ALTER COLUMN "language" SET DEFAULT 'en-US'""",
            ],
            reverse_sql=[
                """ALTER TABLE "user" ALTER COLUMN "profile_display_name" DROP DEFAULT""",
                """ALTER TABLE "user" ALTER COLUMN "language" DROP DEFAULT""",
            ],
        ),
    ]
