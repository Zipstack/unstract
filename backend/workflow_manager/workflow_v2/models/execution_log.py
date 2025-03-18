import uuid

from django.db import models
from utils.models.base_model import BaseModel
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.models import WorkflowExecution


class ExecutionLog(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # TODO: Deprecated field, retained for backward compatibility
    # Remove after old logs are rotated from the system
    # Will be NULL for new records, use `wf_execution` instead
    execution_id = models.UUIDField(
        editable=False,
        db_comment="Execution ID (deprecated, refer wf_execution instead)",
        null=True,
    )
    wf_execution = models.ForeignKey(
        WorkflowExecution,
        on_delete=models.CASCADE,
        editable=False,
        db_comment="Foreign key from WorkflowExecution model",
        related_name="execution_logs",
        null=True,
        blank=True,
    )
    file_execution = models.ForeignKey(
        WorkflowFileExecution,
        on_delete=models.CASCADE,
        db_index=True,
        editable=False,
        db_comment="Foreign key from WorkflowFileExecution model",
        related_name="execution_logs",
        null=True,
        blank=True,
    )
    data = models.JSONField(db_comment="Execution log data")
    event_time = models.DateTimeField(db_comment="Execution log event time")

    def __str__(self):
        return (
            f"Execution ID: {str(self.wf_execution)}, Message: {self.data}, "
            f"Event time: {self.event_time}"
        )

    class Meta:
        verbose_name = "Execution Log"
        verbose_name_plural = "Execution Logs"
        db_table = "execution_log"
