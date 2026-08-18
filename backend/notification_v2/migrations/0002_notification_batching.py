import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account_v2", "0001_initial"),
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
        migrations.CreateModel(
            name="NotificationBuffer",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                (
                    "webhook_url",
                    models.URLField(
                        db_comment="Denormalized destination URL; grouping key."
                    ),
                ),
                (
                    "payload",
                    models.JSONField(
                        db_comment="Pre-structured execution data (type, pipeline_id, pipeline_name, status, additional_data; optional execution_id, error_message, is_failure, timestamp) — NOT a final rendered message. The renderer formats this at dispatch time."
                    ),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[("SLACK", "Slack"), ("API", "Api")],
                        db_comment="SLACK / API — drives renderer selection at flush time.",
                        max_length=50,
                    ),
                ),
                (
                    "auth_sig",
                    models.CharField(
                        db_comment="SHA-256 hex of (auth_type + auth_key + auth_header), computed at enqueue time. Grouping key — never store raw credentials here.",
                        max_length=64,
                    ),
                ),
                (
                    "flush_after",
                    models.DateTimeField(
                        db_comment="now() at enqueue + the org's effective club interval (per-org Configuration override, else the NOTIFICATION_CLUB_INTERVAL default), precomputed at enqueue. Read-at-enqueue contract: changing the interval only affects rows enqueued afterward."
                    ),
                ),
                ("dispatched_at", models.DateTimeField(blank=True, null=True)),
                (
                    "dispatch_attempts",
                    models.PositiveIntegerField(
                        db_comment="Count of times this row has been claimed for dispatch (incremented on each PENDING -> SENDING transition). Bounds the reaper reclaim loop: at NOTIFICATION_MAX_DISPATCH_ATTEMPTS the row is dead-lettered instead of re-dispatched, so a lost terminal callback cannot redeliver forever.",
                        default=0,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SENDING", "Sending"),
                            ("DISPATCHED", "Dispatched"),
                            ("DEAD_LETTER", "Dead letter"),
                        ],
                        db_comment="Lifecycle: PENDING -> SENDING (claimed by a flush tick) -> DISPATCHED on success / DEAD_LETTER on retry exhaustion or once dispatch_attempts hits NOTIFICATION_MAX_DISPATCH_ATTEMPTS. A SENDING row whose lease expires is reclaimed back to PENDING by the reaper.",
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                (
                    "notification",
                    models.ForeignKey(
                        db_comment="Source Notification. Cascade-delete is intentional: removing a Notification expresses intent to stop all future deliveries, including buffered ones.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="buffer_rows",
                        to="notification_v2.notification",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        db_comment="Tenant scope. Mandatory grouping key — prevents cross-tenant leakage at flush time.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_buffer_rows",
                        to="account_v2.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Notification Buffer",
                "verbose_name_plural": "Notification Buffers",
                "db_table": "notification_buffer",
            },
        ),
        migrations.AddIndex(
            model_name="notificationbuffer",
            index=models.Index(
                condition=models.Q(("status", "PENDING")),
                fields=[
                    "organization",
                    "webhook_url",
                    "auth_sig",
                    "platform",
                    "flush_after",
                ],
                name="idx_notif_buffer_pending",
            ),
        ),
    ]
