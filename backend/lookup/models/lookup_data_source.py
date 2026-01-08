"""LookupDataSource model for managing reference data versions."""

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from utils.models.base_model import BaseModel

User = get_user_model()


class LookupDataSourceManager(models.Manager):
    """Custom manager for LookupDataSource."""

    def get_latest_for_project(self, project_id: uuid.UUID):
        """Get the latest data sources for a project.

        Args:
            project_id: UUID of the lookup project

        Returns:
            QuerySet of latest data sources
        """
        return self.filter(project_id=project_id, is_latest=True)

    def get_ready_for_project(self, project_id: uuid.UUID):
        """Get all completed latest data sources for a project.

        Args:
            project_id: UUID of the lookup project

        Returns:
            QuerySet of completed latest data sources
        """
        return self.get_latest_for_project(project_id).filter(
            extraction_status="completed"
        )


class LookupDataSource(BaseModel):
    """Represents a reference data source with version management.

    Each upload creates a new version, with automatic version numbering
    and latest flag management.
    """

    EXTRACTION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    FILE_TYPE_CHOICES = [
        ("pdf", "PDF"),
        ("xlsx", "Excel"),
        ("csv", "CSV"),
        ("docx", "Word"),
        ("txt", "Text"),
        ("json", "JSON"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "lookup.LookupProject",
        on_delete=models.CASCADE,
        related_name="data_sources",
        help_text="Parent Look-Up project",
    )

    # File Information
    file_name = models.CharField(max_length=255, help_text="Original filename")
    file_path = models.TextField(help_text="Path in object storage")
    file_size = models.BigIntegerField(help_text="File size in bytes")
    file_type = models.CharField(
        max_length=50, choices=FILE_TYPE_CHOICES, help_text="Type of file"
    )

    # Extracted Content
    extracted_content_path = models.TextField(
        blank=True, null=True, help_text="Path to extracted text in object storage"
    )
    extraction_status = models.CharField(
        max_length=20,
        choices=EXTRACTION_STATUS_CHOICES,
        default="pending",
        help_text="Status of text extraction",
    )
    extraction_error = models.TextField(
        blank=True, null=True, help_text="Error details if extraction failed"
    )

    # Version Management
    version_number = models.IntegerField(
        default=1, help_text="Version number of this data source (auto-incremented)"
    )
    is_latest = models.BooleanField(
        default=True, help_text="Whether this is the latest version"
    )

    # Upload Information
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="uploaded_lookup_data",
        help_text="User who uploaded this file",
    )

    objects = LookupDataSourceManager()

    class Meta:
        """Model metadata."""

        db_table = "lookup_data_sources"
        ordering = ["-version_number"]
        unique_together = [["project", "version_number"]]
        verbose_name = "Look-Up Data Source"
        verbose_name_plural = "Look-Up Data Sources"
        indexes = [
            models.Index(fields=["project"]),
            models.Index(fields=["project", "is_latest"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["extraction_status"]),
        ]

    def __str__(self) -> str:
        """String representation."""
        return f"{self.project.name} - v{self.version_number} - {self.file_name}"

    def get_file_size_display(self) -> str:
        """Get human-readable file size.

        Returns:
            Formatted file size string (e.g., "51.2 KB")
        """
        size = self.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    @property
    def is_extraction_complete(self) -> bool:
        """Check if extraction is successfully completed."""
        return self.extraction_status == "completed"

    def get_extracted_content(self) -> str | None:
        """Load extracted content from object storage.

        Returns:
            Extracted text content or None if not available.

        Note:
            This is a placeholder - actual implementation will
            load from object storage using extracted_content_path.
        """
        if not self.extracted_content_path or not self.is_extraction_complete:
            return None

        # TODO: Implement actual object storage retrieval
        # For now, return a placeholder
        return f"[Content from {self.extracted_content_path}]"


@receiver(pre_save, sender=LookupDataSource)
def auto_increment_version_and_update_latest(sender, instance, **kwargs):
    """Signal to auto-increment version number and manage is_latest flag.

    This signal:
    1. Auto-increments version_number if not set
    2. Marks all previous versions as not latest
    """
    # Check if this is a new instance by querying the database
    # (instance.pk is always truthy for UUIDField with default=uuid.uuid4)
    is_new = not LookupDataSource.objects.filter(pk=instance.pk).exists()

    if is_new:
        # Get the highest version number for this project
        max_version = LookupDataSource.objects.filter(project=instance.project).aggregate(
            max_version=models.Max("version_number")
        )["max_version"]

        # Always auto-increment version for new instances
        instance.version_number = (max_version or 0) + 1

        # Mark all previous versions as not latest
        LookupDataSource.objects.filter(project=instance.project, is_latest=True).update(
            is_latest=False
        )

        # Ensure new version is marked as latest
        instance.is_latest = True
