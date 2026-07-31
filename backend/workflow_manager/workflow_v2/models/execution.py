import logging
import uuid
from datetime import timedelta

from api_v2.models import APIDeployment
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Q, QuerySet, Sum
from pipeline_v2.models import Pipeline
from tags.models import Tag
from tenant_account_v2.organization_member_service import OrganizationMemberService
from tenant_account_v2.sharing_helpers import resources_visible_via_memberships
from usage_v2.constants import UsageKeys
from usage_v2.helper import UsageHelper
from usage_v2.models import Usage
from utils.common_utils import CommonUtils
from utils.models.base_model import BaseModel, BaseModelManager
from utils.user_context import UserContext

from workflow_manager.execution.dto import ExecutionCache
from workflow_manager.execution.execution_cache_utils import ExecutionCacheUtils
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import Workflow

logger = logging.getLogger(__name__)


EXECUTION_ERROR_LENGTH = 256


class WorkflowExecutionManager(BaseModelManager):
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

        Service accounts see all executions (org-scoped by view).

        Args:
            user: The user to filter executions for

        Returns:
            QuerySet of executions that the user has permission to access
        """
        if getattr(user, "is_service_account", False):
            org = UserContext.get_organization()
            if org:
                return self.filter(workflow__organization=org)
            return self.all()

        if OrganizationMemberService.is_user_organization_admin(user):
            org = UserContext.get_organization()
            if org:
                return self.filter(workflow__organization=org)
            return self.all()

        # Filter for workflow access (owner or direct viewer via membership).
        # ``created_by`` is audit-only (UN-2202); VIEWER rows replaced shared_users.
        # ``object_id`` is varchar, so resolve the ids via the cast helper rather
        # than a ``memberships`` JOIN (Postgres refuses ``uuid = varchar``).
        workflow_filter = Q(
            workflow_id__in=resources_visible_via_memberships(Workflow, user)
        )

        # Filter for API deployments the user can access
        api_filter = Q(
            pipeline_id__in=resources_visible_via_memberships(APIDeployment, user)
        )

        # Filter for Pipelines the user can access
        pipeline_filter = Q(
            pipeline_id__in=resources_visible_via_memberships(Pipeline, user)
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
    queue_message_id = models.BigIntegerField(
        editable=False,
        null=True,
        db_comment="pg_queue_message.msg_id for PG-transport executions "
        "(the queue-row handle; task_id stays NULL on the PG path)",
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
    successful_files = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_comment=(
            "Per-run aggregate of files that completed successfully. Written by "
            "the worker callback at terminal state. Null on rows created before "
            "this column was added."
        ),
    )
    failed_files = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_comment=(
            "Per-run aggregate of files that errored. Written by the worker "
            "callback at terminal state. Null on rows created before this "
            "column was added."
        ),
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
            # Partial index over ACTIVE (non-terminal) executions only — see
            # migration 0023. Keeps the hot "is there an in-flight execution of
            # this workflow?" lookup (WHERE workflow_id=… AND status IN active)
            # O(active) instead of O(all-history-for-workflow). The predicate is
            # the COMPLEMENT of the terminal set: the *index* stays usable if a new
            # *active* status is added, but the callers use a frozen positive
            # status IN ('PENDING','EXECUTING') list — so a new active status is
            # indexed yet not returned until every caller's list is updated too.
            # Only a new *terminal* status needs this predicate updated; the literal
            # is kept in sync with ExecutionStatus.terminal_values() by
            # tests/test_active_execution_index.py.
            models.Index(
                fields=["workflow_id"],
                name="we_active_by_workflow_idx",
                condition=~Q(status__in=["COMPLETED", "STOPPED", "ERROR"]),
            ),
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
        from django.db import transaction

        should_release_rate_limit = False
        with transaction.atomic():
            # Lock the row and read the PERSISTED marker + status together, so routing
            # AND the write are atomic. Never trust the (possibly stale) in-memory
            # self.queue_message_id: a PG row snapshotted before dispatch recorded its
            # handle, mis-routed to an unlocked legacy full save(), would write NULL
            # back into queue_message_id and permanently disable every guard. Under
            # this lock a concurrent _record_dispatch_handle serializes after us.
            locked = (
                WorkflowExecution.objects.select_for_update()
                .filter(pk=self.pk)
                .values("queue_message_id", "status", "attempts")
                .first()
            )
            if locked is None:
                return
            if locked["queue_message_id"] is None:
                should_release_rate_limit = self._apply_legacy_update(
                    status, error, increment_attempt
                )
            else:
                should_release_rate_limit = self._apply_pg_guarded_update(
                    locked, status, error, increment_attempt
                )
        if should_release_rate_limit and self.pipeline_id:
            # Release the slot only once the status write is DURABLE. update_execution()
            # has its own atomic(), but callers (update_status, the PG reaper's
            # _recover_one_stuck_pg_execution) wrap it in an OUTER transaction with
            # further writes (file aggregates, cascade). Firing the Redis release inline
            # would free the rate-limit slot even if that outer txn later rolls back —
            # freed slot + un-persisted status. transaction.on_commit fires on the
            # OUTERMOST commit and is dropped on rollback; in autocommit (no surrounding
            # txn) it runs immediately. So the happy path is unchanged for both
            # transports, only the rollback leak is closed.
            transaction.on_commit(self._release_api_deployment_rate_limit)

    def _apply_legacy_update(
        self,
        status: ExecutionStatus | None,
        error: str | None,
        increment_attempt: bool,
    ) -> bool:
        """Celery-path (queue_message_id NULL) — unchanged full save(); runs inside the
        caller's locked transaction. Returns whether to release the rate-limit slot.
        """
        should_release = False
        if status is not None:
            status = ExecutionStatus(status)
            self.status = status.value
            if status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.ERROR,
                ExecutionStatus.STOPPED,
            ]:
                self.execution_time = CommonUtils.time_since(self.created_at, 3)
                should_release = True
        if error:
            self.error_message = error[:EXECUTION_ERROR_LENGTH]
        if increment_attempt:
            self.attempts += 1
        self.save()
        return should_release

    def _apply_pg_guarded_update(
        self,
        locked: dict,
        status: ExecutionStatus | None,
        error: str | None,
        increment_attempt: bool,
    ) -> bool:
        """PG-path terminal-one-way guarded write, inside the caller's row lock. Refuses
        a revert of a protected-terminal (COMPLETED/STOPPED) status — ERROR stays
        correctable — while still applying error / increment_attempt. Field-scoped
        (``update_fields``) so a stale object can never clobber counters or the marker,
        and the post-save cache publishes the status actually persisted. Returns whether
        to release the rate-limit slot.
        """
        committed = locked["status"]
        should_release = False
        update_fields: list[str] = []
        if status is not None:
            status_fields, should_release = self._apply_guarded_status(
                ExecutionStatus(status), committed, error, increment_attempt
            )
            update_fields.extend(status_fields)
        if error:
            self.error_message = error[:EXECUTION_ERROR_LENGTH]
            update_fields.append("error_message")
        if increment_attempt:
            # Increment from the locked committed value, not the stale in-memory one.
            self.attempts = locked["attempts"] + 1
            update_fields.append("attempts")
        if update_fields:
            update_fields.append("modified_at")
            self.save(update_fields=update_fields)
        return should_release

    def _apply_guarded_status(
        self,
        status: ExecutionStatus,
        committed: str,
        error: str | None,
        increment_attempt: bool,
    ) -> tuple[list[str], bool]:
        """Apply the status change under the terminal-one-way guard.

        Returns ``(update_fields, should_release_rate_limit)``. On a refused revert of
        a protected-terminal (COMPLETED/STOPPED) row, keeps ``self.status == committed``
        and returns ``([], False)`` — the caller still applies error / increment.
        """
        if (
            committed in ExecutionStatus.protected_terminal_values()
            and status.value != committed
        ):
            logger.warning(
                "update_execution: refusing to revert protected status '%s' with "
                "'%s' for execution %s (stale-writer guard); error=%s "
                "increment_attempt=%s still applied",
                committed,
                status.value,
                self.id,
                bool(error),
                increment_attempt,
            )
            self.status = committed  # keep self + post-save cache consistent with DB
            return [], False

        self.status = status.value
        fields = ["status"]
        should_release = False
        if status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.ERROR,
            ExecutionStatus.STOPPED,
        ]:
            self.execution_time = CommonUtils.time_since(self.created_at, 3)
            fields.append("execution_time")
            should_release = True
        return fields, should_release

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

    @classmethod
    def get_last_run_statuses(cls, pipeline_id: uuid.UUID, limit: int = 5) -> list[dict]:
        """Fetch the last N execution statuses for a pipeline.

        Computes PARTIAL_SUCCESS dynamically when execution completed but has
        both successful and failed files.

        Args:
            pipeline_id: UUID of the pipeline (ETL or API deployment)
            limit: Number of recent executions to fetch (default 5)

        Returns:
            List of dicts with execution_id, status, timestamp, and file counts.
            Ordered oldest to newest (for left-to-right timeline display).
        """
        executions = cls.objects.filter(pipeline_id=pipeline_id).order_by("-created_at")[
            :limit
        ]

        result = []
        for e in executions:
            successful = e.successful_files or 0
            failed = e.failed_files or 0

            # Compute display_status: PARTIAL_SUCCESS if completed with mixed results
            display_status = e.status
            if e.status == "COMPLETED" and failed > 0 and successful > 0:
                display_status = "PARTIAL_SUCCESS"

            result.append(
                {
                    "execution_id": str(e.id),
                    "status": display_status,
                    "timestamp": e.created_at.isoformat() if e.created_at else None,
                    "successful_files": successful,
                    "failed_files": failed,
                }
            )

        # Reverse to get oldest first (left-to-right timeline)
        return list(reversed(result))
