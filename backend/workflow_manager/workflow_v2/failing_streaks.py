"""Which pipelines and API deployments are failing right now.

A row is failing when every one of its last five runs failed (the same five
runs the lists draw as status dots, see ``WorkflowExecution.get_last_run_statuses``).
For each failing row this reports how many runs in a row have failed, when that
streak began and when the row last succeeded.

Shared by the dashboard attention feed (PB-T14) and the list aggregates (PB-T13),
so both name the same rows.
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
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class FailingStreak:
    """One failing row."""

    row: Any
    failures_in_a_row: int
    failing_since: datetime
    last_failure: datetime
    last_success: datetime | None


def _runs(pipeline_id: Any) -> QuerySet[WorkflowExecution]:
    return WorkflowExecution.objects.filter(pipeline_id=pipeline_id)


def failing_streaks(rows: QuerySet[Any]) -> list[FailingStreak]:
    """Return the failing rows of ``rows``, newest failure first.

    ``rows`` is a queryset of ``Pipeline`` or ``APIDeployment``; executions are
    matched on ``WorkflowExecution.pipeline_id``. Rows with fewer than five runs
    are never failing. One query, whatever the number of rows: each row's
    lookups are correlated subqueries on the ``(pipeline_id, -created_at)``
    index.
    """
    recent = _runs(OuterRef("pk")).order_by("-created_at")
    last_success = Subquery(
        _runs(OuterRef("pk"))
        .filter(status=_SUCCEEDED)
        .order_by("-created_at")
        .values("created_at")[:1]
    )
    # Failures since the last success; a row that never succeeded counts all.
    streak = _runs(OuterRef("pk")).filter(
        status=_FAILED,
        created_at__gt=Coalesce(OuterRef("_last_success"), Value(_EPOCH)),
    )
    annotated = rows.annotate(
        _recent_statuses=ArraySubquery(recent.values("status")[:FAILING_STREAK_RUNS]),
        _last_failure=Subquery(recent.values("created_at")[:1]),
        _last_success=last_success,
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

    streaks = []
    for row in annotated:
        statuses = row._recent_statuses
        if len(statuses) < FAILING_STREAK_RUNS or any(s != _FAILED for s in statuses):
            continue
        streaks.append(
            FailingStreak(
                row=row,
                failures_in_a_row=row._failures_in_a_row,
                failing_since=row._failing_since,
                last_failure=row._last_failure,
                last_success=row._last_success,
            )
        )
    streaks.sort(key=lambda s: (s.last_failure, str(s.row.pk)), reverse=True)
    return streaks
