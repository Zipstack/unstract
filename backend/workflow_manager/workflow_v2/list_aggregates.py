"""Status, owner, last-run and failing rules for the deployment and pipeline lists.

The list filters and the ``aggregate/`` counts both read from here, so a count
always matches the list filtered the same way.

A row's status comes from its latest finished run (COMPLETED, STOPPED or
ERROR); PENDING and EXECUTING runs are skipped. ``inactive`` wins over the run.
STOPPED counts as ``error``, as the run callback reports it as a failure. A
COMPLETED run counts as ``success`` even when some of its files failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from django.db.models import (
    Case,
    CharField,
    Count,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from permissions.roles import ResourceRole
from tenant_account_v2.sharing_helpers import resources_visible_via_memberships

from unstract.core.data_models import ExecutionStatus
from workflow_manager.workflow_v2.failing_streaks import (
    FailingStreak,
    failing_only,
    failing_streaks,
)
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

FAILING_LIST_CAP = 100

_FINISHED = sorted(ExecutionStatus.terminal_values())
_SUCCEEDED = ExecutionStatus.COMPLETED.value
_ERRORED = [ExecutionStatus.ERROR.value, ExecutionStatus.STOPPED.value]


class RowStatus(StrEnum):
    """A row's status in the list."""

    SUCCESS = "success"
    ERROR = "error"
    NEVER_RUN = "never_run"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class RowFields:
    """Model field names the rules read. ``schedule`` enables ``not_scheduled``."""

    active: str
    last_run: str
    schedule: str | None = None


@dataclass(frozen=True)
class ListFilters:
    """Optional list filters; the defaults filter nothing."""

    status: RowStatus | None = None
    owner: int | None = None
    last_run_after: datetime | None = None
    last_run_before: datetime | None = None
    failing: bool = False


@dataclass(frozen=True)
class StatusCounts:
    """Rows per ``RowStatus``."""

    success: int = 0
    error: int = 0
    never_run: int = 0
    inactive: int = 0

    @property
    def total(self) -> int:
        return self.success + self.error + self.never_run + self.inactive


@dataclass(frozen=True)
class ListAggregate:
    """Counts over a list's rows and its failing rows, capped, newest first."""

    by_status: StatusCounts
    failing_count: int
    failing: list[FailingStreak]
    not_scheduled: int | None = None

    @property
    def total(self) -> int:
        return self.by_status.total


def with_status(rows: QuerySet[Any], fields: RowFields) -> QuerySet[Any]:
    """Annotate each row's ``RowStatus`` value as ``_row_status``."""
    latest_finished = (
        WorkflowExecution.objects.filter(pipeline_id=OuterRef("pk"), status__in=_FINISHED)
        .order_by("-created_at")
        .values("status")[:1]
    )
    return rows.annotate(_latest_finished=Subquery(latest_finished)).annotate(
        _row_status=Case(
            When(**{fields.active: False}, then=Value(RowStatus.INACTIVE.value)),
            When(_latest_finished=_SUCCEEDED, then=Value(RowStatus.SUCCESS.value)),
            When(_latest_finished__in=_ERRORED, then=Value(RowStatus.ERROR.value)),
            default=Value(RowStatus.NEVER_RUN.value),
            output_field=CharField(),
        )
    )


def failing_rows(rows: QuerySet[Any], fields: RowFields) -> QuerySet[Any]:
    """Active rows whose last five finished runs all ended in ERROR."""
    return failing_only(rows.filter(**{fields.active: True}))


def apply_list_filters(
    rows: QuerySet[Any], filters: ListFilters, fields: RowFields
) -> QuerySet[Any]:
    """``rows`` narrowed by ``filters``; returned as is when none is set."""
    if filters.status is not None:
        rows = with_status(rows, fields).filter(_row_status=filters.status.value)
    if filters.owner is not None:
        owned = resources_visible_via_memberships(
            rows.model, filters.owner, role=ResourceRole.OWNER
        )
        rows = rows.filter(pk__in=owned)
    if filters.last_run_after is not None:
        rows = rows.filter(**{f"{fields.last_run}__gte": filters.last_run_after})
    if filters.last_run_before is not None:
        rows = rows.filter(**{f"{fields.last_run}__lte": filters.last_run_before})
    if filters.failing:
        rows = failing_rows(rows, fields)
    return rows


def count_by_status(rows: QuerySet[Any], fields: RowFields) -> StatusCounts:
    """How many of ``rows`` are in each status. One query."""
    grouped = (
        with_status(rows, fields).order_by().values("_row_status").annotate(n=Count("pk"))
    )
    return StatusCounts(**{group["_row_status"]: group["n"] for group in grouped})


def _count_not_scheduled(rows: QuerySet[Any], fields: RowFields) -> int | None:
    """Active rows with a blank schedule, for models that have one."""
    if fields.schedule is None:
        return None
    blank = Q(**{f"{fields.schedule}__isnull": True}) | Q(**{fields.schedule: ""})
    count: int = rows.filter(blank, **{fields.active: True}).count()
    return count


def aggregate_rows(rows: QuerySet[Any], fields: RowFields) -> ListAggregate:
    """Counts and failing rows over ``rows``, the list's filtered queryset.

    A fixed number of queries, whatever the number of rows.
    """
    # Re-selected by pk so the list's distinct, ordering and annotations stay out.
    scoped = rows.model.objects.filter(pk__in=rows.values("pk"))
    owners_loaded = scoped.prefetch_related("memberships__user")
    # failing_streaks applies failing_only, so this is the failing_rows rule.
    streaks = failing_streaks(owners_loaded.filter(**{fields.active: True}))
    return ListAggregate(
        by_status=count_by_status(scoped, fields),
        failing_count=len(streaks),
        failing=streaks[:FAILING_LIST_CAP],
        not_scheduled=_count_not_scheduled(scoped, fields),
    )
