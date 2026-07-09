import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("global_api_deployment_key", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="globalapideploymentkey",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                db_comment="Foreign key reference to the Organization model.",
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="account_v2.organization",
            ),
        ),
    ]
