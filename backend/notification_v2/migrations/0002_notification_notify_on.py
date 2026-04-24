from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notification_v2", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="notify_on",
            field=models.CharField(
                max_length=50,
                choices=[
                    ("ALL", "All"),
                    ("FAILURES_ONLY", "Failures only"),
                    ("SUCCESS_ONLY", "Success only"),
                ],
                default="ALL",
                db_comment=(
                    "Controls which run outcomes trigger this notification. ALL "
                    "(default) preserves the historical 'notify on every "
                    "completion' behavior; FAILURES_ONLY fires only on failed "
                    "runs (ERROR for API deployments, FAILURE for ETL "
                    "pipelines); SUCCESS_ONLY fires only on successful runs."
                ),
            ),
        ),
    ]
