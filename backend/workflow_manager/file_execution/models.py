import uuid

from django.db import models
from utils.models.base_model import BaseModel
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

FILE_NAME_LENGTH = 255
FILE_PATH_LENGTH = 255
HASH_LENGTH = 64
MIME_TYPE_LENGTH = 128


class WorkflowFileExecution(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_execution = models.ForeignKey(
        WorkflowExecution,
        on_delete=models.CASCADE,
        db_index=True,
        editable=False,
        db_comment="Foreign key from WorkflowExecution   model",
    )
    file_name = models.CharField(
        max_length=FILE_NAME_LENGTH, db_comment="Name of the file"
    )
    file_path = models.CharField(
        max_length=FILE_PATH_LENGTH, null=True, db_comment="Full Path of the file"
    )
    file_size = models.BigIntegerField(
        null=True, db_comment="Size of the file in bytes"
    )
    file_hash = models.CharField(
        max_length=HASH_LENGTH, db_comment="Hash of the file content"
    )
    mime_type = models.CharField(
        max_length=MIME_TYPE_LENGTH,
        blank=True,
        null=True,
        db_comment="MIME type of the file",
    )
    status = models.TextField(
        choices=ExecutionStatus.choices(),
        db_comment="Current status of the execution",
    )
    execution_time = models.FloatField(
        null=True, db_comment="Execution time in seconds"
    )
    execution_error = models.TextField(
        blank=True, null=True, db_comment="Error message if execution failed"
    )

    def __str__(self):
        return (
            f"WorkflowFileExecution: {self.file_name} "
            f"(WorkflowExecution: {self.workflow_execution})"
        )

    class Meta:
        verbose_name = "Workflow File Execution"
        verbose_name_plural = "Workflow File Executions"
        db_table = "workflow_file_execution"
        indexes = [
            models.Index(
                fields=["workflow_execution", "file_hash"],
                name="workflow_file_hash_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["workflow_execution", "file_hash", "file_path"],
                name="unique_workflow_file_hash_path",
            ),
        ]
