import uuid

from django.db import models
from tags.models import Tag
from utils.models.base_model import BaseModel

EXECUTION_ERROR_LENGTH = 256


class WorkflowExecution(BaseModel):
    class Mode(models.TextChoices):
        INSTANT = "INSTANT", "will be executed immediately"
        QUEUE = "QUEUE", "will be placed in a queue"

    class Method(models.TextChoices):
        DIRECT = "DIRECT", " Execution triggered manually"
        SCHEDULED = "SCHEDULED", "Scheduled execution"

    class Type(models.TextChoices):
        COMPLETE = "COMPLETE", "For complete execution"
        STEP = "STEP", "For step-by-step execution "

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # TODO: Make as foreign key to access the instance directly
    pipeline_id = models.UUIDField(
        editable=False,
        null=True,
        db_comment="ID of the associated pipeline, if applicable",
    )
    task_id = models.UUIDField(
        editable=False,
        null=True,
        db_comment="task id of asynchronous execution",
    )
    workflow_id = models.UUIDField(
        editable=False, db_comment="Id of workflow to be executed"
    )
    execution_mode = models.CharField(
        choices=Mode.choices, db_comment="Mode of execution"
    )
    execution_method = models.CharField(
        choices=Method.choices, db_comment="Method of execution"
    )
    execution_type = models.CharField(
        choices=Type.choices, db_comment="Type of execution"
    )
    execution_log_id = models.CharField(
        default="", editable=False, db_comment="Execution log events Id"
    )
    # TODO: Restrict with an enum
    status = models.CharField(default="", db_comment="Current status of execution")
    result_acknowledged = models.BooleanField(
        default=False, db_comment="Result acknowledged"
    )
    error_message = models.CharField(
        max_length=EXECUTION_ERROR_LENGTH,
        blank=True,
        default="",
        db_comment="Details of encountered errors",
    )
    attempts = models.IntegerField(default=0, db_comment="number of attempts taken")
    execution_time = models.FloatField(
        default=0, db_comment="execution time in seconds"
    )
    tags = models.ManyToManyField(Tag, related_name="workflow_executions", blank=True)

    class Meta:
        verbose_name = "Workflow Execution"
        verbose_name_plural = "Workflow Executions"
        db_table = "workflow_execution"

    @property
    def tag_names(self) -> list[str]:
        """Return a list of tag names associated with the workflow execution."""
        return list(self.tags.values_list("name", flat=True))

    def __str__(self) -> str:
        return (
            f"Workflow execution: {self.id} ("
            f"pipeline ID: {self.pipeline_id}, "
            f"workflow iD: {self.workflow_id}, "
            f"execution method: {self.execution_method}, "
            f"status: {self.status}, "
            f"error message: {self.error_message})"
        )
