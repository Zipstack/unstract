"""Delayed visibility for pg_queue_message (UN-3843).

Adds ``available_at`` + the ``scheduled`` state so a dispatch can defer delivery
(Celery ``countdown``/``eta`` parity). Additive and inert: existing rows and every
existing enqueue resolve to ``available_at = now()`` / ``state = 'ready'``, which is
exactly today's behaviour.

**Why the hand-written ``SET DEFAULT now()`` step.** Django's ``AddField`` adds the
column with a one-off literal default and then DROPS that default, leaving the column
``NOT NULL`` with no DB default. The workers' enqueue is raw SQL with an explicit
column list that does not mention ``available_at``
(``queue_backend/pg_queue/client.py``) — so without a persistent DB default, every
worker enqueue would fail with a not-null violation the moment this migration landed,
and would keep failing regardless of deploy order. The DB default also encodes the
right semantic on its own: a row that does not ask to be deferred is available now.

Ordering is therefore safe in both directions (migrate-before-workers or
workers-before-migrate), which is the posture the rest of the PG rollout assumes.
"""

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pg_queue", "0001_initial_squashed"),
    ]

    operations = [
        # Widen the closed state enum BEFORE anything can write 'scheduled'.
        migrations.RemoveConstraint(
            model_name="pgqueuemessage",
            name="pg_queue_message_state_valid",
        ),
        migrations.AddField(
            model_name="pgqueuemessage",
            name="available_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        # Restore a PERSISTENT default so the workers' raw INSERT (which omits this
        # column) keeps working. Django dropped the AddField default above; state_
        # operations is empty because this changes only the DB, not the model Django
        # tracks — the model keeps its Python-level default and stays in sync.
        migrations.RunSQL(
            sql="ALTER TABLE pg_queue_message ALTER COLUMN available_at SET DEFAULT now()",
            reverse_sql=(
                "ALTER TABLE pg_queue_message ALTER COLUMN available_at DROP DEFAULT"
            ),
            state_operations=[],
        ),
        migrations.AddIndex(
            model_name="pgqueuemessage",
            index=models.Index(
                models.F("available_at"),
                condition=models.Q(("state", "scheduled")),
                name="pg_queue_message_scheduled_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="pgqueuemessage",
            constraint=models.CheckConstraint(
                check=models.Q(("state__in", ["ready", "claimed", "scheduled"])),
                name="pg_queue_message_state_valid",
            ),
        ),
    ]
