import logging
import uuid
from datetime import timedelta
from typing import Any

from django.db import models
from utils.common_utils import CommonUtils
from utils.models.base_model import BaseModel, BaseModelManager

from unstract.core.stage_timings import WorkflowStage
from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.workflow_v2.enums import ExecutionStatus

logger = logging.getLogger(__name__)

FILE_NAME_LENGTH = 255
FILE_PATH_LENGTH = 255
HASH_LENGTH = 64
MIME_TYPE_LENGTH = 128


class WorkflowFileExecutionManager(BaseModelManager):
    def get_or_create_file_execution(
        self,
        workflow_execution: Any,
        file_hash: FileHash,
        is_api: bool = False,
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
    # UN-3451 narrowed this to processing time only (it previously also counted
    # the queue wait, because update_status ignored the worker's measurement).
    # On a retry or resumed run it is the last attempt's span, not the sum of
    # all attempts. For elapsed time from queued to done, read
    # `stage_timings["total"]`.
    #
    # The db_comment is deliberately left as-is: changing it emits an
    # AlterField whose SQL is `ALTER COLUMN ... TYPE double precision`, and
    # Postgres can rewrite this whole high-volume table under an ACCESS
    # EXCLUSIVE lock for what is only a comment. Not worth it — the semantics
    # are documented here and on `update_status`.
    execution_time = models.FloatField(null=True, db_comment="Execution time in seconds")
    stage_timings = models.JSONField(
        null=True,
        blank=True,
        db_comment=(
            "Per-stage execution timing breakdown in seconds "
            "(queue wait, source fetch, tool execution with its extraction/"
            "indexing/prompt split, destination, finalization)"
        ),
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
        status: ExecutionStatus | str,
        execution_error: str = None,
        execution_time: float = None,
        stage_timings: dict[str, Any] = None,
    ) -> None:
        """Updates the status and execution details of an input file.

        Args:
        execution_file: The `WorkflowExecutionFile` object to update
        status: The new status of the file (ExecutionStatus enum or string)
        execution_time: Seconds the worker spent processing the file. When
            given it is stored as-is; the queue wait is deliberately not
            included (see the field's db_comment). Omitted only by callers
            that have no measurement, which fall back to elapsed-since-created.
        execution_error: (Optional) Error message if processing failed
        stage_timings: (Optional) Per-stage timing payload from the worker

        Return:
            The updated `WorkflowExecutionInputFile` object
        """
        status = ExecutionStatus(status)
        self.status = status.value
        # Prefer the worker's own measurement: time_since(created_at) also
        # counts the queue wait before a worker picked the file up, which is
        # not time spent processing it.
        if execution_time is not None:
            self.execution_time = execution_time
        elif status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.ERROR,
            ExecutionStatus.STOPPED,
        ]:
            self.execution_time = CommonUtils.time_since(self.created_at, 3)

        # isinstance, not truthiness alone: the field is a bare JSONField on the
        # internal API, so a list/string/number would otherwise be persisted and
        # then have to be defended against by every reader.
        if isinstance(stage_timings, dict) and stage_timings:
            self.stage_timings = self._finalize_stage_timings(stage_timings)

        self.execution_error = execution_error
        self.save()

    def _finalize_stage_timings(self, stage_timings: dict[str, Any]) -> dict[str, Any]:
        """Add the queue wait and restate the totals to span every stage.

        The worker cannot measure queue wait — it has no view of ``created_at``
        — and its own total covers only the span it ran for.

        ``total`` is therefore **not** ``execution_time``: it is the file's
        whole lifetime, ``queue_wait + execution_time``. ``execution_time``
        covers processing only, so using it as the total would leave the stage
        map summing to more than the total whenever a file waited in the queue
        — percentages over 100% and a negative remainder. Readers divide by
        ``total``, so it has to span everything ``stages`` holds.
        """
        try:
            payload = dict(stage_timings)
            stages = dict(payload.get("stages") or {})

            queue_wait = 0.0
            started_at = payload.pop("started_at", None)
            if (
                isinstance(started_at, (int, float))
                and not isinstance(started_at, bool)
                and self.created_at
            ):
                measured = started_at - self.created_at.timestamp()
                # Clock skew between the backend and the worker can push this
                # negative; omit it rather than report a negative wait.
                if measured > 0:
                    queue_wait = round(measured, 3)
                    stages[WorkflowStage.QUEUE_WAIT] = queue_wait

            payload["stages"] = stages

            processing = self.execution_time
            if isinstance(processing, (int, float)) and processing > 0:
                total = round(processing + queue_wait, 3)
                payload["total"] = total
                unaccounted = round(total - sum(stages.values()), 3)
                # Stages can still outrun the total if two spans overlap;
                # report nothing rather than a number that cannot be true.
                payload["unaccounted"] = unaccounted if unaccounted > 0 else 0.0
            return payload
        except Exception:
            logger.warning(
                "Failed to finalize stage timings for file execution %s",
                self.id,
                exc_info=True,
            )
            return stage_timings

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
            models.Index(
                fields=["workflow_execution", "file_hash", "file_path", "status"],
                name="wf_file_hash_path_status_idx",
            ),
            models.Index(
                fields=[
                    "workflow_execution",
                    "provider_file_uuid",
                    "file_path",
                    "status",
                ],
                name="wf_provider_uuid_path_stat_idx",
            ),
            # Every other index on this table is prefixed by the workflow_execution
            # FK column, so none can serve a status + created_at filter. Serves both
            # get_failed_pages and, since UN-3973 narrowed the source window, the
            # COMPLETED path. See migration 0007.
            models.Index(
                fields=["status", "created_at"],
                name="wfe_status_created_idx",
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
        return self.status is not None and self.status == ExecutionStatus.COMPLETED.value

    def update(
        self,
        file_hash: str = None,
        fs_metadata: dict[str, Any] = None,
        mime_type: str = None,
    ) -> None:
        """Updates the file execution details.

        Args:
            file_hash: (Optional) Hash of the file content
            fs_metadata: (Optional) File system metadata
            mime_type: (Optional) MIME type of the file

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
        if mime_type is not None:
            self.mime_type = mime_type
            update_fields.append("mime_type")
        if update_fields:  # Save only if there's an actual update
            self.save(update_fields=update_fields)
