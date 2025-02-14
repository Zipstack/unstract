import logging
import uuid
from typing import Optional

from api_v2.models import APIDeployment
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from pipeline_v2.models import Pipeline
from tags.models import Tag
from utils.models.base_model import BaseModel
from workflow_manager.workflow_v2.models import Workflow

logger = logging.getLogger(__name__)


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
    # TODO: Make as foreign key to access the instance directly
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
        default=False,
        db_comment=(
            "To track if result is acknowledged by user - "
            "used mainly by API deployments"
        ),
    )
    total_files = models.PositiveIntegerField(
        default=0, verbose_name="Total files", db_comment="Number of files to process"
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
        indexes = [
            models.Index(fields=["workflow_id", "-created_at"]),
            models.Index(fields=["pipeline_id", "-created_at"]),
        ]

    @property
    def tag_names(self) -> list[str]:
        """Return a list of tag names associated with the workflow execution."""
        return list(self.tags.values_list("name", flat=True))

    @property
    def workflow_name(self) -> Optional[str]:
        """Obtains the workflow's name associated to this execution."""
        try:
            return Workflow.objects.get(id=self.workflow_id).workflow_name
        except ObjectDoesNotExist:
            logger.warning(
                f"Expected workflow ID '{self.workflow_id}' to exist but missing"
            )
            return None

    @property
    def pipeline_name(self) -> Optional[str]:
        """Obtains the pipeline's name associated to this execution.
        It could be ETL / TASK / API pipeline, None returned if there's no such pipeline
        """
        if not self.pipeline_id:
            return None

        try:
            return APIDeployment.objects.get(id=self.pipeline_id).display_name
        except ObjectDoesNotExist:
            pass

        try:
            return Pipeline.objects.get(id=self.pipeline_id).pipeline_name
        except ObjectDoesNotExist:
            pass

        return None

    def __str__(self) -> str:
        return (
            f"Workflow execution: {self.id} ("
            f"pipeline ID: {self.pipeline_id}, "
            f"workflow iD: {self.workflow_id}, "
            f"status: {self.status}, "
            f"files: {self.total_files}, "
            f"error message: {self.error_message})"
        )
