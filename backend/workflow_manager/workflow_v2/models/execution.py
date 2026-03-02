import logging
import uuid
from datetime import timedelta

from api_v2.models import APIDeployment
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Q, QuerySet, Sum
from pipeline_v2.models import Pipeline
from tags.models import Tag
from usage_v2.constants import UsageKeys
from usage_v2.models import Usage
from usage_v2.helper import UsageHelper
from utils.common_utils import CommonUtils
from utils.models.base_model import BaseModel

from workflow_manager.execution.dto import ExecutionCache
from workflow_manager.execution.execution_cache_utils import ExecutionCacheUtils
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import Workflow

logger = logging.getLogger(__name__)


EXECUTION_ERROR_LENGTH = 256


class WorkflowExecutionManager(models.Manager):
    """Custom manager for WorkflowExecution model to handle user-specific filtering."""

    def for_user(self, user) -> QuerySet:
        """Filter user's workflow executions with proper access control.

        Returns executions where the user has access to:
        - The workflow (created by user OR shared with user) AND/OR
        - The pipeline/API deployment (created by user OR shared with user)

        This handles independent sharing scenarios:
        1. Workflow shared but not API deployment -> User can see workflow-only executions
        2. API deployment shared but not workflow -> User can see those API executions
        3. Both shared -> User can see all executions
        4. Neither shared -> User cannot see executions

        Args:
            user: The user to filter executions for

        Returns:
            QuerySet of executions that the user has permission to access
        """
        # Filter for workflow access
        workflow_filter = Q(workflow__created_by=user) | Q(workflow__shared_users=user)

        # Filter for API deployments the user can access
        api_filter = Q(
            pipeline_id__in=models.Subquery(
                APIDeployment.objects.filter(
                    Q(created_by=user) | Q(shared_users=user)
                ).values("id")
            )
        )

        # Filter for Pipelines the user can access
        pipeline_filter = Q(
            pipeline_id__in=models.Subquery(
                Pipeline.objects.filter(Q(created_by=user) | Q(shared_users=user)).values(
                    "id"
                )
            )
        )

        # Combine deployment filters
        deployment_filter = api_filter | pipeline_filter

        # User can see executions if they have access to:
        # 1. The workflow AND execution has no pipeline (workflow-level execution)
        # 2. The pipeline/API deployment (regardless of workflow access)
        final_filter = (workflow_filter & Q(pipeline_id__isnull=True)) | deployment_filter

        return self.filter(final_filter).distinct()

    def clean_invalid_workflows(self):
        """Remove execution records with invalid workflow references.

        This is a utility method to clean up data when converting from workflow_id to
        a proper foreign key relationship. It deletes any execution records where the
        workflow reference doesn't exist in the database.

        Returns:
            int: Number of deleted records
        """
        # Find executions with no valid workflow reference
        invalid_executions = self.filter(workflow__isnull=True)

        count = invalid_executions.count()
        if count > 0:
            logger.info(
                f"Deleting {count} execution records with invalid workflow references"
            )
            invalid_executions.delete()
        return count


class WorkflowExecution(BaseModel):
    # Use the custom manager
    objects = WorkflowExecutionManager()

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
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        editable=False,
        db_comment="Workflow to be executed",
        related_name="workflow_executions",
        null=True,
        db_column="workflow_id",  # Reuse the existing column name
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
            "To track if result is acknowledged by user - used mainly by API deployments"
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
    execution_time = models.FloatField(default=0, db_comment="execution time in seconds")
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
    def workflow_name(self) -> str | None:
        """Obtains the workflow's name associated to this execution."""
        if self.workflow:
            return self.workflow.workflow_name
        return None

    @property
    def pipeline_name(self) -> str | None:
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
    def aggregated_usage_cost(self) -> float | None:
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

    @property
    def aggregated_total_pages_processed(self) -> int | None:
        """Retrieve aggregated total pages processed for this execution.

        Returns:
            int | None: Total pages processed across all file executions,
            or None if no page usage data exists.
        """

        file_execution_ids = list(self.file_executions.values_list("id", flat=True))
        if not file_execution_ids:
            return None

        return UsageHelper.get_aggregated_pages_processed(
            run_ids=[str(fid) for fid in file_execution_ids]
        )

    @property
    def is_completed(self) -> bool:
        return ExecutionStatus.is_completed(self.status)

    @property
    def organization_id(self) -> str | None:
        """Get the organization ID from the associated workflow."""
        if (
            self.workflow
            and hasattr(self.workflow, "organization")
            and self.workflow.organization
        ):
            return str(self.workflow.organization.organization_id)
        return None

    def __str__(self) -> str:
        return (
            f"Workflow execution: {self.id} ("
            f"pipeline ID: {self.pipeline_id}, "
            f"workflow: {self.workflow}, "
            f"status: {self.status}, "
            f"files: {self.total_files}, "
            f"error message: {self.error_message})"
        )

    def update_execution(
        self,
        status: ExecutionStatus | None = None,
        error: str | None = None,
        increment_attempt: bool = False,
    ) -> None:
        """Update the execution status and related fields.

        Args:
            status (Optional[ExecutionStatus], optional): New execution status. Defaults to None.
            error (Optional[str], optional): Error message if any. Defaults to None.
            increment_attempt (bool, optional): Whether to increment attempt counter. Defaults to False.
        """
        should_release_rate_limit = False

        if status is not None:
            status = ExecutionStatus(status)
            self.status = status.value
            if status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.ERROR,
                ExecutionStatus.STOPPED,
            ]:
                self.execution_time = CommonUtils.time_since(self.created_at, 3)
                should_release_rate_limit = True

        if error:
            self.error_message = error[:EXECUTION_ERROR_LENGTH]
        if increment_attempt:
            self.attempts += 1

        self.save()

        # Release rate limit slot for API deployment executions after save
        if should_release_rate_limit and self.pipeline_id:
            self._release_api_deployment_rate_limit()

    def _release_api_deployment_rate_limit(self) -> None:
        """Release rate limit slot for API deployment executions.

        Checks if this execution is for an API deployment and releases
        the rate limit slot if applicable.
        """
        try:
            # Check if this is an API deployment execution
            api_deployment = APIDeployment.objects.filter(id=self.pipeline_id).first()
            if api_deployment and api_deployment.organization:
                from api_v2.rate_limiter import APIDeploymentRateLimiter

                APIDeploymentRateLimiter.release_slot(
                    str(api_deployment.organization.organization_id), str(self.id)
                )
        except Exception as e:
            # Log but don't fail the execution update for rate limit release errors
            logger.exception(
                f"Failed to release rate limit slot for execution {self.id}: {e}"
            )

    def update_execution_err(self, err_msg: str = "") -> None:
        """Update execution status to ERROR with an error message.

        Args:
            err_msg (str, optional): Error message to store. Defaults to "".
        """
        self.update_execution(status=ExecutionStatus.ERROR, error=err_msg)

    def _handle_execution_cache(self):
        if not ExecutionCacheUtils.is_execution_exists(
            workflow_id=self.workflow.id, execution_id=self.id
        ):
            execution_cache = ExecutionCache(
                workflow_id=self.workflow.id,
                execution_id=self.id,
                total_files=self.total_files,
                status=self.status,
            )
            ExecutionCacheUtils.create_execution(
                execution=execution_cache,
            )
        else:
            ExecutionCacheUtils.update_status(
                workflow_id=self.workflow.id, execution_id=self.id, status=self.status
            )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._handle_execution_cache()
