# Generated by Django 4.2.1 on 2024-12-12 05:41

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("workflow_v2", "0002_remove_workflow_llm_response_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowFileExecution",
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
                    "file_name",
                    models.CharField(db_comment="Name of the file", max_length=255),
                ),
                (
                    "file_path",
                    models.CharField(
                        db_comment="Full Path of the file", max_length=255, null=True
                    ),
                ),
                (
                    "file_size",
                    models.BigIntegerField(
                        db_comment="Size of the file in bytes", null=True
                    ),
                ),
                (
                    "file_hash",
                    models.CharField(
                        db_comment="Hash of the file content", max_length=64
                    ),
                ),
                (
                    "mime_type",
                    models.CharField(
                        blank=True,
                        db_comment="MIME type of the file",
                        max_length=128,
                        null=True,
                    ),
                ),
                (
                    "status",
                    models.TextField(
                        choices=[
                            ("PENDING", "PENDING"),
                            ("INITIATED", "INITIATED"),
                            ("QUEUED", "QUEUED"),
                            ("READY", "READY"),
                            ("EXECUTING", "EXECUTING"),
                            ("COMPLETED", "COMPLETED"),
                            ("STOPPED", "STOPPED"),
                            ("ERROR", "ERROR"),
                        ],
                        db_comment="Current status of the execution",
                    ),
                ),
                (
                    "execution_time",
                    models.FloatField(
                        db_comment="Execution time in seconds", null=True
                    ),
                ),
                (
                    "execution_error",
                    models.TextField(
                        blank=True,
                        db_comment="Error message if execution failed",
                        null=True,
                    ),
                ),
                (
                    "workflow_execution",
                    models.ForeignKey(
                        db_comment="Foreign key from WorkflowExecution   model",
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="workflow_v2.workflowexecution",
                    ),
                ),
            ],
            options={
                "verbose_name": "Workflow File Execution",
                "verbose_name_plural": "Workflow File Executions",
                "db_table": "workflow_file_execution",
                "indexes": [
                    models.Index(
                        fields=["workflow_execution", "file_hash"],
                        name="workflow_file_hash_idx",
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="workflowfileexecution",
            constraint=models.UniqueConstraint(
                fields=("workflow_execution", "file_hash", "file_path"),
                name="unique_workflow_file_hash_path",
            ),
        ),
    ]