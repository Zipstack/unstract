"""Stuck executions: PENDING/EXECUTING runs with no activity past a threshold."""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, OuterRef, QuerySet, Subquery
from django.db.models.functions import Greatest
from django.utils import timezone

from workflow_manager.execution.entity import entity_condition
from workflow_manager.execution.enum import ExecutionEntity
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models import WorkflowExecution

ACTIVE_STATUSES = (ExecutionStatus.PENDING.value, ExecutionStatus.EXECUTING.value)


@dataclass(frozen=True)
class StuckCount:
    """Stuck executions visible to a caller, in total and per entity."""

    threshold_seconds: int
    total: int
    counts: dict[str, int]


def stuck_threshold_seconds() -> int:
    return int(settings.STUCK_EXECUTION_THRESHOLD_SECONDS)


def stuck_executions(queryset: QuerySet) -> QuerySet:
    """Narrow ``queryset`` to stuck runs, annotated with ``stuck_since``.

    ``stuck_since`` is the last activity: the later of the run's own
    ``modified_at`` and its newest file row's ``modified_at``.
    """
    cutoff = timezone.now() - timedelta(seconds=stuck_threshold_seconds())
    last_file_at = (
        WorkflowFileExecution.objects.filter(workflow_execution=OuterRef("pk"))
        .order_by("-modified_at")
        .values("modified_at")[:1]
    )
    # Postgres GREATEST skips NULL, so a run with no files uses its own time.
    return (
        queryset.filter(status__in=ACTIVE_STATUSES, modified_at__lt=cutoff)
        .annotate(stuck_since=Greatest("modified_at", Subquery(last_file_at)))
        .filter(stuck_since__lt=cutoff)
    )


def count_stuck(queryset: QuerySet) -> StuckCount:
    """Count the stuck runs in ``queryset``, in one query."""
    per_entity = {
        entity.value: Count("pk", filter=entity_condition(entity))
        for entity in ExecutionEntity
    }
    counts = WorkflowExecution.objects.filter(
        pk__in=stuck_executions(queryset).values("pk")
    ).aggregate(total=Count("pk"), **per_entity)
    total = counts.pop("total")
    return StuckCount(
        threshold_seconds=stuck_threshold_seconds(), total=total, counts=counts
    )
