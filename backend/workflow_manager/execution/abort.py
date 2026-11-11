"""Abort running executions: stop the run, keep processed files, audit it."""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from api_v2.models import APIDeployment
from api_v2.utils import APIDeploymentUtils
from django.db import transaction
from django.db.models import Count, DurationField, ExpressionWrapper, F, Q, QuerySet
from django.db.models.functions import Extract, Now
from django.utils import timezone
from permissions.roles import ResourceRole
from pipeline_v2.models import Pipeline
from pipeline_v2.notification import PipelineNotification
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import record_platform_event
from tenant_account_v2.organization_member_service import OrganizationMemberService
from tenant_account_v2.sharing_helpers import resources_visible_via_memberships

from workflow_manager.execution.entity import entity_annotation
from workflow_manager.execution.enum import AbortOutcome
from workflow_manager.execution.execution_cache_utils import ExecutionCacheUtils
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution

logger = logging.getLogger(__name__)

ABORT_ERROR_MESSAGE = "Execution aborted"
MAX_ABORT_IDS = 100


@dataclass(frozen=True)
class AbortResult:
    """Outcome for one id. ``status`` is ``None`` when not permitted or failed."""

    id: UUID
    outcome: AbortOutcome
    status: str | None


@dataclass(frozen=True)
class AbortReport:
    """Results in request order, with a count per outcome."""

    results: list[AbortResult]

    def _count(self, outcome: AbortOutcome) -> int:
        return sum(1 for result in self.results if result.outcome == outcome)

    @property
    def aborted(self) -> int:
        return self._count(AbortOutcome.ABORTED)

    @property
    def already_finished(self) -> int:
        return self._count(AbortOutcome.ALREADY_FINISHED)

    @property
    def not_permitted(self) -> int:
        return self._count(AbortOutcome.NOT_PERMITTED)

    @property
    def failed(self) -> int:
        return self._count(AbortOutcome.FAILED)


def abort_executions(request: Any, ids: list[UUID]) -> AbortReport:
    """Abort each id the caller may abort; one transaction per id."""
    unique_ids = list(dict.fromkeys(ids))
    permitted = _abortable_entities(request.user, unique_ids)
    results = [
        _abort_or_fail(request, execution_id, permitted[execution_id])
        if execution_id in permitted
        else AbortResult(execution_id, AbortOutcome.NOT_PERMITTED, None)
        for execution_id in unique_ids
    ]
    return AbortReport(results)


def _abortable_entities(user: Any, ids: list[UUID]) -> dict[UUID, str | None]:
    """Map each id ``user`` may abort to its entity, in one query.

    Owners of the run's pipeline or API deployment (or of its workflow, for a
    run without one), org admins and service accounts may abort.
    """
    rows = (
        _abortable(user)
        .filter(pk__in=ids)
        .annotate(entity=entity_annotation())
        .values_list("pk", "entity")
    )
    return dict(rows)


def _abortable(user: Any) -> QuerySet:
    visible = WorkflowExecution.objects.for_user(user)
    if getattr(user, "is_service_account", False):
        return visible
    if OrganizationMemberService.is_user_organization_admin(user):
        return visible
    return visible.filter(_owner_condition(user))


def _owner_condition(user: Any) -> Q:
    def owned(model: Any) -> QuerySet:
        return resources_visible_via_memberships(
            model, user, role=str(ResourceRole.OWNER)
        )

    return (
        Q(pipeline_id__isnull=True, workflow_id__in=owned(Workflow))
        | Q(pipeline_id__in=owned(APIDeployment))
        | Q(pipeline_id__in=owned(Pipeline))
    )


def _abort_or_fail(request: Any, execution_id: UUID, entity: str | None) -> AbortResult:
    """Abort one id, so its failure cannot lose the other ids' outcomes."""
    try:
        return _abort_one(request, execution_id, entity)
    except Exception:
        logger.exception("Failed to abort execution %s", execution_id)
        _restore_cached_status(execution_id)
        return AbortResult(execution_id, AbortOutcome.FAILED, None)


def _restore_cached_status(execution_id: UUID) -> None:
    """Republish the stored status, so a rolled-back abort leaves no STOPPED cached."""
    try:
        with transaction.atomic():
            # Locked, so a concurrent status write publishes after this one.
            execution = (
                WorkflowExecution.objects.select_for_update(no_key=True)
                .filter(pk=execution_id)
                .first()
            )
            if execution is None or not ExecutionCacheUtils.is_execution_exists(
                workflow_id=execution.workflow_id, execution_id=execution.id
            ):
                return
            ExecutionCacheUtils.update_status(
                workflow_id=execution.workflow_id,
                execution_id=execution.id,
                status=execution.status,
            )
    except Exception:
        logger.exception(
            "Failed to restore the cached status of execution %s", execution_id
        )


def _abort_one(request: Any, execution_id: UUID, entity: str | None) -> AbortResult:
    """Stop one execution under its row lock, then record the audit event."""
    with transaction.atomic():
        execution = (
            WorkflowExecution.objects.select_for_update(no_key=True, of=("self",))
            .select_related("workflow")
            .filter(pk=execution_id)
            .first()
        )
        if execution is None:
            return AbortResult(execution_id, AbortOutcome.NOT_PERMITTED, None)
        if execution.status in ExecutionStatus.terminal_values():
            return AbortResult(
                execution_id, AbortOutcome.ALREADY_FINISHED, execution.status
            )
        previous_status = execution.status
        execution.update_execution(
            status=ExecutionStatus.STOPPED, error=ABORT_ERROR_MESSAGE, row_locked=True
        )
        _stop_open_files(execution)
        write_file_counts(execution)
        # After commit, so a rolled-back abort reports nothing.
        transaction.on_commit(lambda: _report_abort(execution), robust=True)
    _record_abort(request, execution, previous_status, entity)
    return AbortResult(execution_id, AbortOutcome.ABORTED, execution.status)


def _stop_open_files(execution: WorkflowExecution) -> None:
    """Mark file rows not yet terminal STOPPED; finished rows keep their status."""
    elapsed = ExpressionWrapper(Now() - F("created_at"), output_field=DurationField())
    stopped = (
        WorkflowFileExecution.objects.filter(workflow_execution=execution)
        .exclude(status__in=ExecutionStatus.terminal_values())
        .update(
            status=ExecutionStatus.STOPPED.value,
            execution_error=ABORT_ERROR_MESSAGE,
            execution_time=Extract(elapsed, "epoch"),
        )
    )
    logger.info(
        "Aborted execution %s; stopped %s open file execution(s)", execution.id, stopped
    )


def write_file_counts(execution: WorkflowExecution) -> None:
    """Save the run's file counts from its rows; anything not completed is failed."""
    counts = WorkflowFileExecution.objects.filter(workflow_execution=execution).aggregate(
        total=Count("pk"),
        completed=Count("pk", filter=Q(status=ExecutionStatus.COMPLETED.value)),
    )
    execution.total_files = max(execution.total_files, counts["total"])
    execution.successful_files = counts["completed"]
    execution.failed_files = execution.total_files - counts["completed"]
    execution.save(update_fields=["total_files", "successful_files", "failed_files"])


def _report_abort(execution: WorkflowExecution) -> None:
    """Report the ended run to its pipeline or API deployment.

    The abort does this because a dead worker's run gets no callback.
    """
    try:
        pipeline = Pipeline.objects.filter(pk=execution.pipeline_id).first()
        if pipeline is not None:
            _report_to_pipeline(pipeline, execution)
            return
        deployment = APIDeployment.objects.filter(pk=execution.pipeline_id).first()
        if deployment is not None:
            APIDeploymentUtils.send_notification(
                api=deployment, workflow_execution=execution
            )
    except Exception:
        logger.exception(
            "Failed to report aborted execution %s to %s",
            execution.id,
            execution.pipeline_id,
        )


def _report_to_pipeline(pipeline: Pipeline, execution: WorkflowExecution) -> None:
    """Notify subscribers; the pipeline's own status follows only its newest run."""
    try:
        _save_pipeline_status(pipeline, execution)
    except Exception:
        # Subscribers are still notified.
        logger.exception(
            "Failed to save pipeline %s status for aborted execution %s",
            pipeline.id,
            execution.id,
        )
    PipelineNotification(
        pipeline=pipeline,
        execution_id=execution.id,
        error_message=execution.error_message,
    ).send()


def _save_pipeline_status(pipeline: Pipeline, execution: WorkflowExecution) -> None:
    """Set the last-run status to failure, unless the pipeline has a newer run."""
    pipeline.last_run_status = Pipeline.PipelineStatus.FAILURE
    newer_runs = WorkflowExecution.objects.filter(
        pipeline_id=execution.pipeline_id, created_at__gt=execution.created_at
    )
    if not newer_runs.exists():
        pipeline.last_run_time = timezone.now()
        pipeline.save(update_fields=["last_run_status", "last_run_time"])


def _record_abort(
    request: Any, execution: WorkflowExecution, previous_status: str, entity: str | None
) -> None:
    pipeline_id = str(execution.pipeline_id) if execution.pipeline_id else None
    record_platform_event(
        action=Action.EXECUTION_ABORTED,
        target_type=TargetType.EXECUTION,
        target_id=execution.id,
        target_name=execution.workflow_name or "",
        request=request,
        summary=f"was {previous_status}",
        metadata={
            "previous_status": previous_status,
            "pipeline_id": pipeline_id,
            "entity": entity,
        },
    )
