# Generated manually

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("adapter_processor_v2", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("account_v2", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgenticProject",
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
                    "name",
                    models.CharField(db_comment="Project name", max_length=255),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True, db_comment="Project description", null=True
                    ),
                ),
                (
                    "canary_fields",
                    models.JSONField(
                        blank=True,
                        db_comment="Test documents for regression detection",
                        null=True,
                    ),
                ),
                (
                    "wizard_completed",
                    models.BooleanField(
                        db_comment="Whether initial wizard setup is complete",
                        default=False,
                    ),
                ),
                (
                    "agent_llm",
                    models.ForeignKey(
                        blank=True,
                        db_comment="LLM adapter for agent operations (summarization, tuning)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agentic_projects_agent",
                        to="adapter_processor_v2.adapterinstance",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agentic_projects_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "extractor_llm",
                    models.ForeignKey(
                        blank=True,
                        db_comment="LLM adapter for extraction operations",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agentic_projects_extractor",
                        to="adapter_processor_v2.adapterinstance",
                    ),
                ),
                (
                    "lightweight_llm",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Lightweight LLM for comparison and classification tasks",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agentic_projects_lightweight",
                        to="adapter_processor_v2.adapterinstance",
                    ),
                ),
                (
                    "llmwhisperer",
                    models.ForeignKey(
                        blank=True,
                        db_comment="LLMWhisperer adapter for document processing",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agentic_projects_llmwhisperer",
                        to="adapter_processor_v2.adapterinstance",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agentic_projects_modified",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Project",
                "verbose_name_plural": "Agentic Projects",
                "db_table": "agentic_project",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AgenticDocument",
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
                    "original_filename",
                    models.CharField(
                        db_comment="Original filename of uploaded document",
                        max_length=255,
                    ),
                ),
                (
                    "stored_path",
                    models.TextField(
                        db_comment="Path where document is stored in file system"
                    ),
                ),
                (
                    "size_bytes",
                    models.BigIntegerField(
                        db_comment="Size of document file in bytes", null=True
                    ),
                ),
                (
                    "pages",
                    models.IntegerField(db_comment="Number of pages in document"),
                ),
                (
                    "uploaded_at",
                    models.DateTimeField(
                        auto_now_add=True, db_comment="When document was uploaded"
                    ),
                ),
                (
                    "raw_text",
                    models.TextField(
                        blank=True,
                        db_comment="Extracted text content from document",
                        null=True,
                    ),
                ),
                (
                    "highlight_metadata",
                    models.JSONField(
                        blank=True,
                        db_comment="LLMWhisperer highlight metadata",
                        null=True,
                    ),
                ),
                (
                    "processing_job_id",
                    models.CharField(
                        blank=True,
                        db_comment="Celery task ID for async processing",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "processing_error",
                    models.TextField(
                        blank=True,
                        db_comment="Error message if processing failed",
                        null=True,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Document",
                "verbose_name_plural": "Agentic Documents",
                "db_table": "agentic_document",
                "ordering": ["-uploaded_at"],
            },
        ),
        migrations.CreateModel(
            name="AgenticSchema",
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
                    "json_schema",
                    models.TextField(
                        db_comment="Generated JSON schema for extraction"
                    ),
                ),
                (
                    "version",
                    models.IntegerField(db_comment="Schema version number"),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_comment="Whether this is the active schema", default=True
                    ),
                ),
                (
                    "created_by_agent",
                    models.CharField(
                        db_comment="Which agent created this schema (uniformer/finalizer)",
                        max_length=50,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="schemas",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Schema",
                "verbose_name_plural": "Agentic Schemas",
                "db_table": "agentic_schema",
                "ordering": ["-version"],
            },
        ),
        migrations.CreateModel(
            name="AgenticSummary",
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
                    "summary_text",
                    models.TextField(db_comment="Generated summary of document"),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="summaries",
                        to="agentic_studio_v2.agenticdocument",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="summaries",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Summary",
                "verbose_name_plural": "Agentic Summaries",
                "db_table": "agentic_summary",
            },
        ),
        migrations.CreateModel(
            name="AgenticVerifiedData",
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
                    "data",
                    models.JSONField(
                        db_comment="Ground truth data verified by human"
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="verified_data",
                        to="agentic_studio_v2.agenticdocument",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="verified_data",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Verified Data",
                "verbose_name_plural": "Agentic Verified Data",
                "db_table": "agentic_verified_data",
            },
        ),
        migrations.CreateModel(
            name="AgenticPromptVersion",
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
                    "version",
                    models.IntegerField(db_comment="Prompt version number"),
                ),
                (
                    "short_desc",
                    models.CharField(
                        db_comment="Brief description of this version", max_length=255
                    ),
                ),
                (
                    "long_desc",
                    models.TextField(
                        blank=True,
                        db_comment="Detailed description of changes",
                        null=True,
                    ),
                ),
                (
                    "prompt_text",
                    models.TextField(db_comment="The actual prompt text"),
                ),
                (
                    "accuracy",
                    models.FloatField(
                        db_comment="Overall accuracy score (0.0 to 1.0)", null=True
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_comment="Whether this is the active version",
                        default=False,
                    ),
                ),
                (
                    "created_by_agent",
                    models.CharField(
                        db_comment="Which agent created this version",
                        max_length=50,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "parent_version",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Previous version this was derived from",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="child_versions",
                        to="agentic_studio_v2.agenticpromptversion",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="prompt_versions",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Prompt Version",
                "verbose_name_plural": "Agentic Prompt Versions",
                "db_table": "agentic_prompt_version",
                "ordering": ["-version"],
            },
        ),
        migrations.CreateModel(
            name="AgenticExtractedData",
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
                    "data",
                    models.JSONField(
                        db_comment="Extracted data from LLM"
                    ),
                ),
                (
                    "extraction_job_id",
                    models.CharField(
                        blank=True,
                        db_comment="Celery task ID for async extraction",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extracted_data",
                        to="agentic_studio_v2.agenticdocument",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extracted_data",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
                (
                    "prompt_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extractions",
                        to="agentic_studio_v2.agenticpromptversion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Extracted Data",
                "verbose_name_plural": "Agentic Extracted Data",
                "db_table": "agentic_extracted_data",
            },
        ),
        migrations.CreateModel(
            name="AgenticComparisonResult",
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
                    "field_path",
                    models.CharField(
                        db_comment="Dot-separated path to field in schema",
                        max_length=255,
                    ),
                ),
                (
                    "match",
                    models.BooleanField(
                        db_comment="Whether extracted matches verified"
                    ),
                ),
                (
                    "normalized_extracted",
                    models.TextField(
                        blank=True,
                        db_comment="Normalized extracted value",
                        null=True,
                    ),
                ),
                (
                    "normalized_verified",
                    models.TextField(
                        blank=True,
                        db_comment="Normalized verified value",
                        null=True,
                    ),
                ),
                (
                    "error_type",
                    models.CharField(
                        blank=True,
                        db_comment="Type of error if mismatch",
                        max_length=50,
                        null=True,
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comparison_results",
                        to="agentic_studio_v2.agenticdocument",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comparison_results",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
                (
                    "prompt_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comparison_results",
                        to="agentic_studio_v2.agenticpromptversion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Comparison Result",
                "verbose_name_plural": "Agentic Comparison Results",
                "db_table": "agentic_comparison_result",
            },
        ),
        migrations.CreateModel(
            name="AgenticExtractionNote",
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
                    "field_path",
                    models.CharField(
                        db_comment="Dot-separated path to field in schema",
                        max_length=255,
                    ),
                ),
                (
                    "note_text",
                    models.TextField(
                        db_comment="Human note about extraction"
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extraction_notes",
                        to="agentic_studio_v2.agenticdocument",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extraction_notes",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Extraction Note",
                "verbose_name_plural": "Agentic Extraction Notes",
                "db_table": "agentic_extraction_note",
            },
        ),
        migrations.CreateModel(
            name="AgenticLog",
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
                    "level",
                    models.CharField(
                        db_comment="Log level (INFO, WARNING, ERROR)",
                        max_length=20,
                    ),
                ),
                (
                    "message",
                    models.TextField(db_comment="Log message"),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        db_comment="Additional structured metadata",
                        null=True,
                    ),
                ),
                (
                    "timestamp",
                    models.DateTimeField(
                        auto_now_add=True, db_comment="When log was created"
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="agentic_studio_v2.agenticproject",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Log",
                "verbose_name_plural": "Agentic Logs",
                "db_table": "agentic_log",
                "ordering": ["-timestamp"],
            },
        ),
        migrations.CreateModel(
            name="AgenticSetting",
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
                    "key",
                    models.CharField(
                        db_comment="Setting key", max_length=100, unique=True
                    ),
                ),
                (
                    "value",
                    models.TextField(db_comment="Setting value"),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        db_comment="Description of setting",
                        null=True,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_comment="Foreign key reference to the Organization model.",
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="account_v2.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agentic Setting",
                "verbose_name_plural": "Agentic Settings",
                "db_table": "agentic_setting",
            },
        ),
        migrations.AddConstraint(
            model_name="agenticschema",
            constraint=models.UniqueConstraint(
                fields=("project", "version"),
                name="unique_project_schema_version",
            ),
        ),
        migrations.AddConstraint(
            model_name="agenticpromptversion",
            constraint=models.UniqueConstraint(
                fields=("project", "version"),
                name="unique_project_prompt_version",
            ),
        ),
    ]
