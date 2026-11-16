"""Give `extractor` its `choices` and take away its `default`.

Schema no-op on Postgres: Django keeps both `choices` and a field `default` in
Python only -- no CHECK constraint, no column DEFAULT -- so this `AlterField`
changes model state and emits no DDL that touches data. Existing rows keep
whatever they recorded, including the `kv` rows migration 0002 back-filled.

The `default="kv"` this removes was correct when 0002 added the column (the
API accepted one extractor and it was always `kv`) and became a trap once
`table` existed: an omitted `extractor=` filed a table job as `kv`, which IS a
valid key in `STAGE_NAMES_BY_EXTRACTOR`, so the status endpoint returned the KV
stage list and dropped `table_extraction` silently. See the field comment on
the model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent_kv", "0004_pg_periodic_tasks"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agentkvjob",
            name="extractor",
            field=models.CharField(
                choices=[("kv", "Kv"), ("table", "Table")], max_length=32
            ),
        ),
    ]
