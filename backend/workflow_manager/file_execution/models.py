import uuid
from datetime import timedelta
from typing import Any

from django.db import models
from utils.common_utils import CommonUtils
from utils.models.base_model import BaseModel

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.enums import ExecutionStatus

FILE_NAME_LENGTH = 255
FILE_PATH_LENGTH = 255
HASH_LENGTH = 64
MIME_TYPE_LENGTH = 128


class WorkflowFileExecutionManager(models.Manager):
    def get_or_create_file_execution(
        self,
        workflow_execution: Any,
        file_hash: FileHash,
        connection_type: WorkflowEndpoint.ConnectionType,
    ) -> "WorkflowFileExecution":
        """Retrieves or creates a new input file record for a workflow execution.

        Args:
            workflow_execution: The `WorkflowExecution` object
                associated with this file.
            file_hash: The `FileHash` object containing file metadata.
            file_path: (Optional) The full path of the input file.

        Returns:
            The `WorkflowFileExecution` object.
        """
        is_api = connection_type == WorkflowEndpoint.ConnectionType.API
        # Determine file path based on connection type
        execution_file_path = file_hash.file_path if not is_api else None

        lookup_fields = {
            "workflow_execution": workflow_execution,
            "file_path": execution_file_path,
        }

        if file_hash.file_hash:
            lookup_fields["file_hash"] = file_hash.file_hash
        elif file_hash.provider_file_uuid:
            lookup_fields["provider_file_uuid"] = file_hash.provider_file_uuid

        execution_file, is_created = self.get_or_create(**lookup_fields)

        if is_created:
            self._update_execution_file(execution_file, file_hash)

        return execution_file

    def _update_execution_file(
        self, execution_file: "WorkflowFileExecution", file_hash: FileHash
    ) -> None:
        """Updates the attributes of a newly created WorkflowFileExecution object."""
        execution_file.file_name = file_hash.file_name
        execution_file.file_size = file_hash.file_size
        execution_file.mime_type = file_hash.mime_type
        execution_file.provider_file_uuid = file_hash.provider_file_uuid
        execution_file.fs_metadata = file_hash.fs_metadata
        execution_file.save()


class WorkflowFileExecution(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_execution = models.ForeignKey(
        "workflow_v2.WorkflowExecution",
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
    file_size = models.BigIntegerField(null=True, db_comment="Size of the file in bytes")
    file_hash = models.CharField(
        max_length=HASH_LENGTH, null=True, db_comment="Hash of the file content"
    )
    provider_file_uuid = models.CharField(
        max_length=HASH_LENGTH,
        null=True,
        db_comment="Unique identifier assigned by the file storage provider",
    )
    fs_metadata = models.JSONField(
        null=True,
        db_comment="Complete metadata of the file retrieved from the file system.",
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
    execution_time = models.FloatField(null=True, db_comment="Execution time in seconds")
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
        """Updates the status and execution details of an input file.

        Args:
        execution_file: The `WorkflowExecutionFile` object to update
        status: The new status of the file
        execution_time: The execution time for processing the file
        execution_error: (Optional) Error message if processing failed

        Return:
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
            models.Index(
                fields=["workflow_execution", "provider_file_uuid"],
                name="workflow_exec_p_uuid_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["workflow_execution", "file_hash", "file_path"],
                name="unique_workflow_file_hash_path",
            ),
            models.UniqueConstraint(
                fields=["workflow_execution", "provider_file_uuid", "file_path"],
                name="unique_workflow_provider_uuid_path",
            ),
        ]

    @property
    def is_completed(self) -> bool:
        """Check if the execution status is completed.

        Returns:
            bool: True if the execution status is completed, False otherwise.
        """
        return self.status is not None and self.status == ExecutionStatus.COMPLETED

    def update(
        self,
        file_hash: str = None,
        fs_metadata: dict[str, Any] = None,
    ) -> None:
        """Updates the file execution details.

        Args:
            file_hash: (Optional) Hash of the file content

        Returns:
            None
        """
        update_fields = []

        if file_hash is not None:
            self.file_hash = file_hash
            update_fields.append("file_hash")
        if fs_metadata is not None:
            self.fs_metadata = fs_metadata
            update_fields.append("fs_metadata")
        if update_fields:  # Save only if there's an actual update
            self.save(update_fields=update_fields)
