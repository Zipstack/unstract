import uuid
from datetime import timedelta
from typing import Optional

from django.db import models
from utils.common_utils import CommonUtils
from utils.models.base_model import BaseModel
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

FILE_NAME_LENGTH = 255
FILE_PATH_LENGTH = 255
HASH_LENGTH = 64
MIME_TYPE_LENGTH = 128


class WorkflowFileExecutionManager(models.Manager):
    def get_or_create_file_execution(
        self,
        workflow_execution: WorkflowExecution,
        file_name: str,
        file_size: int,
        file_hash: str,
        file_path: Optional[str] = None,
        mime_type: Optional[str] = None,
    ):
        """
        Retrieves or creates a new input file record for a workflow execution.

        Args:
        workflow_execution: The `WorkflowExecution` object associated with this file
        file_name: The name of the input file
        file_size: The size of the file in bytes
        file_hash: The hash of the file content
        file_path: (Optional) The full path of the input file
        mime_type: (Optional) MIME type of the file

        return:
            The `WorkflowFileExecution` object
        """
        execution_file: WorkflowFileExecution
        execution_file, is_created = self.get_or_create(
            workflow_execution=workflow_execution,
            file_hash=file_hash,
            file_path=file_path,
        )

        if is_created:
            execution_file.file_name = file_name
            execution_file.file_size = file_size
            execution_file.mime_type = mime_type
            execution_file.save()
        return execution_file


class WorkflowFileExecution(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_execution = models.ForeignKey(
        WorkflowExecution,
        on_delete=models.CASCADE,
        db_index=True,
        editable=False,
        db_comment="Foreign key from WorkflowExecution model",
        related_name="file_executions",
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
        choices=ExecutionStatus.choices,
        db_comment="Current status of the execution",
    )
    execution_time = models.FloatField(
        null=True, db_comment="Execution time in seconds"
    )
    execution_error = models.TextField(
        blank=True, null=True, db_comment="Error message if execution failed"
    )

    # Custom manager
    objects = WorkflowFileExecutionManager()

    def __str__(self):
        return (
            f"WorkflowFileExecution: {self.file_name} "
            f"(WorkflowExecution: {self.workflow_execution})"
        )

    def update_status(
        self,
        status: ExecutionStatus,
        execution_error: str = None,
    ) -> None:
        """
        Updates the status and execution details of an input file.

        Args:
        execution_file: The `WorkflowExecutionFile` object to update
        status: The new status of the file
        execution_time: The execution time for processing the file
        execution_error: (Optional) Error message if processing failed

        return:
            The updated `WorkflowExecutionInputFile` object
        """
        self.status = status

        if (
            status
            in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.ERROR,
                ExecutionStatus.STOPPED,
            ]
            and not self.execution_time
        ):
            self.execution_time = CommonUtils.time_since(self.created_at)

        self.execution_error = execution_error
        self.save()

    @property
    def pretty_file_size(self) -> str:
        """Convert file_size from bytes to human-readable format

        Returns:
            str: File size with a precision of 2 decimals
        """
        return CommonUtils.pretty_file_size(self.file_size)

    @property
    def pretty_execution_time(self) -> str:
        """Convert execution_time from seconds to HH:MM:SS format

        Returns:
            str: Time in HH:MM:SS format
        """
        # Compute execution time for a run that's in progress
        time_in_secs = (
            self.execution_time
            if self.execution_time
            else CommonUtils.time_since(self.created_at)
        )
        return str(timedelta(seconds=time_in_secs)).split(".")[0]

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
