from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notification_v2", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="notify_on_failures",
            field=models.BooleanField(
                default=False,
                db_comment=(
                    "When True, fire only on failed runs — terminal status "
                    "ERROR/STOPPED or any file in the run errored (partial "
                    "failure). When False (default), fire on every terminal "
                    "completion."
                ),
            ),
        ),
    ]
