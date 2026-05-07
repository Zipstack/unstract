import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("account_v2", "0001_initial"),
        ("notification_v2", "0002_notification_notify_on_failures"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="delivery_mode",
            field=models.CharField(
                choices=[("IMMEDIATE", "Immediate"), ("BATCHED", "Batched")],
                default="IMMEDIATE",
                max_length=16,
                db_comment=(
                    "IMMEDIATE fires on every completion (default, unchanged "
                    "behavior). BATCHED buffers events and dispatches a single "
                    "clubbed message per (org, webhook_url, auth_sig) every "
                    "NOTIFICATION_CLUB_INTERVAL."
                ),
            ),
        ),
        migrations.CreateModel(
            name="NotificationBuffer",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "webhook_url",
                    models.URLField(
                        db_comment="Denormalized destination URL; grouping key.",
                    ),
                ),
                (
                    "payload",
                    models.JSONField(
                        db_comment=(
                            "Pre-structured execution data (execution_id, status, "
                            "error_message, pipeline_name, pipeline_type) — NOT a "
                            "final rendered message. The renderer formats this at "
                            "dispatch time."
                        ),
                    ),
                ),
                (
                    "platform",
                    models.CharField(
                        choices=[("SLACK", "Slack"), ("API", "Api")],
                        max_length=50,
                        db_comment=(
                            "SLACK / API — drives renderer selection at flush time."
                        ),
                    ),
                ),
                (
                    "auth_sig",
                    models.CharField(
                        max_length=64,
                        db_comment=(
                            "SHA-256 hex of (auth_type + auth_key + auth_header), "
                            "computed at enqueue time. Grouping key — never store "
                            "raw credentials here."
                        ),
                    ),
                ),
                (
                    "flush_after",
                    models.DateTimeField(
                        db_comment=(
                            "created_at + NOTIFICATION_CLUB_INTERVAL, precomputed "
                            "at enqueue. Read-at-enqueue contract: changing the "
                            "env var only affects rows enqueued after the restart."
                        ),
                    ),
                ),
                ("dispatched_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("DISPATCHED", "Dispatched"),
                            ("DEAD_LETTER", "Dead letter"),
                        ],
                        default="PENDING",
                        max_length=16,
                        db_comment=(
                            "PENDING -> DISPATCHED on success, "
                            "PENDING -> DEAD_LETTER on retry exhaustion."
                        ),
                    ),
                ),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="buffer_rows",
                        to="notification_v2.notification",
                        db_comment=(
                            "Source Notification. Cascade-delete is intentional: "
                            "removing a Notification expresses intent to stop all "
                            "future deliveries, including buffered ones."
                        ),
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_buffer_rows",
                        to="account_v2.organization",
                        db_comment=(
                            "Tenant scope. Mandatory grouping key — prevents "
                            "cross-tenant leakage at flush time."
                        ),
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
                fields=["organization", "webhook_url", "auth_sig", "flush_after"],
                name="idx_notif_buffer_pending",
            ),
        ),
    ]
