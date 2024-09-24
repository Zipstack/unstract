import uuid

from django.db import models


class PageUsage(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Primary key for the usage entry, automatically generated UUID",
    )

    organization_id = models.CharField(
        default="mock_org",
        null=False,
        blank=False,
    )
    file_name = models.CharField(
        max_length=255,
        blank=True,
        db_comment="Name of the file",
    )
    file_type = models.CharField(
        max_length=128,
        blank=True,
        db_comment="Mime type of file",
    )

    run_id = models.CharField(
        max_length=255, blank=True, db_comment="Identifier for the run"
    )

    pages_processed = models.IntegerField(
        db_comment="Number of pages which got processed"
    )
    file_size = models.BigIntegerField(db_comment="Size of the the file")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.file_name)

    class Meta:
        db_table = "page_usage"
        indexes = [
            models.Index(fields=["organization_id"]),
        ]
