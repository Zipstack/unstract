import logging
import uuid
from datetime import timedelta
from typing import Optional

from api_v2.models import APIDeployment
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Sum
from pipeline_v2.models import Pipeline
from tags.models import Tag
from usage_v2.constants import UsageKeys
from usage_v2.models import Usage
from utils.common_utils import CommonUtils
from utils.models.base_model import BaseModel
from workflow_manager.workflow_v2.enums import ExecutionStatus
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
    related_workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        editable=False,
        db_comment="Workflow to be executed",
        related_name="executions",
        null=True,
        db_column="related_wf_id",
    )
    # TODO: Deprecated, remove after migration / log rotation
    workflow_id = models.UUIDField(
        editable=False,
        db_comment="ID of workflow being executed (deprecated)",
        null=True,
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
    status = models.CharField(
        choices=ExecutionStatus.choices,
        db_comment="Current status of the execution",
    )
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
    def workflow(self) -> Optional[Workflow]:
        """Gets the associated workflow.

        First tries the foreign key then falls back to workflow_id.
        """
        if self.related_workflow:
            return self.related_workflow
        elif self.workflow_id:
            try:
                return Workflow.objects.get(id=self.workflow_id)
            except ObjectDoesNotExist:
                logger.warning(
                    f"Expected workflow '{self.workflow_id}' to exist but missing"
                )
                return None
        return None

    @property
    def workflow_name(self) -> Optional[str]:
        """Obtains the workflow's name associated to this execution."""
        if self.workflow:
            return self.workflow.workflow_name
        elif self.workflow_id:
            try:
                return Workflow.objects.get(id=self.workflow_id).workflow_name
            except ObjectDoesNotExist:
                logger.warning(
                    f"Expected workflow ID '{self.workflow_id}' to exist but missing"
                )
                return None
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

    @property
    def get_aggregated_usage_cost(self) -> Optional[float]:
        """Retrieve aggregated cost for the given execution_id.


        Returns:
        Optional[float]: The total cost in dollars if available, else None.

        Raises:
            APIException: For unexpected errors during database operations.
        """
        # Aggregate the cost for the given execution_id
        queryset = Usage.objects.filter(execution_id=self.id)

        if queryset.exists():
            result = queryset.aggregate(cost_in_dollars=Sum(UsageKeys.COST_IN_DOLLARS))
            total_cost = result.get(UsageKeys.COST_IN_DOLLARS)
        else:
            # Handle the case where no usage data is found for the given execution_id
            logger.warning(
                f"Usage data not found for the specified execution_id: {self.id}"
            )
            return None

        logger.debug(
            f"Cost aggregated successfully for execution_id: {self.id}"
            f", Total cost: {total_cost}"
        )

        return total_cost

    def __str__(self) -> str:
        return (
            f"Workflow execution: {self.id} ("
            f"pipeline ID: {self.pipeline_id}, "
            f"workflow: {self.workflow_id}, "
            f"status: {self.status}, "
            f"files: {self.total_files}, "
            f"error message: {self.error_message})"
        )
