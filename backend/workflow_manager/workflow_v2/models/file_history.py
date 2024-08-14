import uuid

from django.db import models
from utils.models.base_model import BaseModel
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.workflow import Workflow

HASH_LENGTH = 64


class FileHistory(BaseModel):
    def is_completed(self) -> bool:
        """Check if the execution status is completed.

        Returns:
            bool: True if the execution status is completed, False otherwise.
        """
        return (
            self.status is not None and self.status == ExecutionStatus.COMPLETED.value
        )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cache_key = models.CharField(
        max_length=HASH_LENGTH,
        db_comment="Hash value of file contents, WF and tool modified times",
    )
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="file_histories",
    )
    status = models.TextField(
        choices=ExecutionStatus.choices(),
        db_comment="Latest status of execution",
    )
    error = models.TextField(
        blank=True,
        default="",
        db_comment="Error message",
    )
    result = models.TextField(blank=True, db_comment="Result from execution")
    metadata = models.TextField(blank=True, db_comment="MetaData from execution")

    class Meta:
        verbose_name = "File History"
        verbose_name_plural = "File Histories"
        db_table = "file_history"
        constraints = [
            models.UniqueConstraint(
                fields=["workflow", "cache_key"],
                name="unique_workflow_cacheKey",
            ),
        ]
