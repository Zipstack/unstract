"""Which pipelines and API deployments are failing right now.

A row is failing when each of its last five finished runs ended in ERROR.
Runs still PENDING or EXECUTING are skipped, so a queued retry does not hide a
row that keeps failing. For each failing row this reports how many finished
runs in a row have failed, when that streak began and when the row last
succeeded.

This is the list status dots' rule (ERROR is the red dot), not
``unstract.core.data_models.is_failure_run``: that one also counts STOPPED and
partly failed runs, which suits failure notifications but would list a pipeline
someone stopped on purpose as broken.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from django.contrib.postgres.expressions import ArraySubquery
from django.db.models import Count, OuterRef, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce

from unstract.core.data_models import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

FAILING_STREAK_RUNS = 5

_FAILED = ExecutionStatus.ERROR.value
_SUCCEEDED = ExecutionStatus.COMPLETED.value
_FINISHED = sorted(ExecutionStatus.terminal_values())
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class FailingStreak:
    """One failing row."""

    row: Any
    failures_in_a_row: int
    failing_since: datetime
    last_failure: datetime
    last_success: datetime | None


def _finished_runs() -> QuerySet[WorkflowExecution]:
    """The outer row's finished runs, newest first."""
    return WorkflowExecution.objects.filter(
        pipeline_id=OuterRef("pk"), status__in=_FINISHED
    ).order_by("-created_at")


def failing_only(rows: QuerySet[Any]) -> QuerySet[Any]:
    """``rows`` whose last five finished runs all ended in ERROR.

    Annotates ``_last_failure``, the latest of those runs.
    """
    finished = _finished_runs()
    return rows.annotate(
        _recent_statuses=ArraySubquery(finished.values("status")[:FAILING_STREAK_RUNS]),
        _last_failure=Subquery(finished.values("created_at")[:1]),
    ).filter(_recent_statuses=[_FAILED] * FAILING_STREAK_RUNS)


def failing_streaks(
    rows: QuerySet[Any],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[FailingStreak]:
    """Return the failing rows of ``rows``, newest failure first.

    ``rows`` is a queryset of ``Pipeline`` or ``APIDeployment``; executions are
    matched on ``WorkflowExecution.pipeline_id``. Rows with fewer than five
    finished runs are never failing. ``start_date`` and ``end_date``, when
    given, bound the latest failure: the failing test always uses the row's
    latest runs, so a past ``end_date`` does not mean "failing as of then".

    One query, whatever the number of rows. The failing test and the range run
    in SQL first, so the streak lookups, which can read a row's whole history,
    are computed only for rows that are failing.
    """
    finished = _finished_runs()
    rows = failing_only(rows)
    if start_date is not None:
        rows = rows.filter(_last_failure__gte=start_date)
    if end_date is not None:
        rows = rows.filter(_last_failure__lte=end_date)

    # The streak is the ERRORs since the newest finished run that was not one.
    streak = finished.filter(
        status=_FAILED,
        created_at__gt=Coalesce(OuterRef("_streak_break"), Value(_EPOCH)),
    )
    annotated = rows.annotate(
        _last_success=Subquery(
            finished.filter(status=_SUCCEEDED).values("created_at")[:1]
        ),
        _streak_break=Subquery(finished.exclude(status=_FAILED).values("created_at")[:1]),
    ).annotate(
        _failing_since=Subquery(streak.order_by("created_at").values("created_at")[:1]),
        _failures_in_a_row=Coalesce(
            Subquery(
                streak.order_by()
                .values("pipeline_id")
                .annotate(n=Count("id"))
                .values("n")[:1]
            ),
            0,
        ),
    )

    streaks = [
        FailingStreak(
            row=row,
            failures_in_a_row=row._failures_in_a_row,
            failing_since=row._failing_since,
            last_failure=row._last_failure,
            last_success=row._last_success,
        )
        for row in annotated
    ]
    streaks.sort(key=lambda s: (s.last_failure, str(s.row.pk)), reverse=True)
    return streaks
