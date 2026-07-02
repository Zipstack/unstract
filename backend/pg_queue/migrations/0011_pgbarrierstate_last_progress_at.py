# Generated for UN-3661 — PG barrier stuck-timeout (progress liveness).

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pg_queue", "0010_pgtaskresult"),
    ]

    operations = [
        # Progress-liveness column for the reaper's fast stuck-detection. Default
        # now() so any row created before this migration is treated as fresh.
        # Deliberately UNINDEXED — written on every barrier decrement, so an index
        # would break the decrement's heap-only-tuple (HOT) update; the reaper
        # seq-scans this tiny (in-flight-only) table cheaply.
        migrations.AddField(
            model_name="pgbarrierstate",
            name="last_progress_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
