from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    """Build the lookup-usage dashboard index without locking the table.

    CONCURRENTLY requires that the migration itself runs outside a
    transaction, hence atomic = False.
    """

    atomic = False

    dependencies = [
        ("usage_v2", "0004_usage_metrics_fields"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="usage",
            index=models.Index(
                fields=["llm_usage_reason", "reference_id", "-created_at"],
                name="idx_usage_reason_ref_created",
            ),
        ),
    ]
