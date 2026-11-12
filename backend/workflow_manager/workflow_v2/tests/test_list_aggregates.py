"""The status, failing, owner and last-run rules behind the list filters and
the ``aggregate/`` counts.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock

from api_v2.api_deployment_views import DEPLOYMENT_ROW_FIELDS
from api_v2.models import APIDeployment
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase
from pipeline_v2.models import Pipeline
from pipeline_v2.views import PIPELINE_ROW_FIELDS
from rest_framework.exceptions import ValidationError

from workflow_manager.workflow_v2 import list_aggregates
from workflow_manager.workflow_v2.list_aggregate_serializers import list_filters_from
from workflow_manager.workflow_v2.list_aggregates import (
    ListFilters,
    RowStatus,
    StatusCounts,
    aggregate_rows,
    apply_list_filters,
    count_by_status,
    with_status,
)
from workflow_manager.workflow_v2.tests.list_rows import (
    COMPLETED,
    ERROR,
    EXECUTING,
    FIVE_ERRORS,
    PENDING,
    STOPPED,
    ListRowsSeed,
)
from workflow_manager.workflow_v2.models.execution import WorkflowExecution


class StatusRuleTests(ListRowsSeed, TestCase):
    def _status_of(self, row: APIDeployment) -> str:
        rows = with_status(APIDeployment.objects.filter(pk=row.pk), DEPLOYMENT_ROW_FIELDS)
        status: str = rows.get()._row_status
        return status

    def test_a_row_without_runs_has_never_run(self) -> None:
        self.assertEqual(self._status_of(self._deployment("fresh")), RowStatus.NEVER_RUN)

    def test_runs_that_never_finished_do_not_count(self) -> None:
        row = self._deployment("orphans")
        self._runs(row, [PENDING, EXECUTING])

        self.assertEqual(self._status_of(row), RowStatus.NEVER_RUN)

    def test_the_latest_finished_run_decides(self) -> None:
        recovered = self._deployment("recovered")
        self._runs(recovered, [ERROR, COMPLETED, PENDING])
        broken = self._deployment("broken")
        self._runs(broken, [COMPLETED, ERROR, EXECUTING])

        self.assertEqual(self._status_of(recovered), RowStatus.SUCCESS)
        self.assertEqual(self._status_of(broken), RowStatus.ERROR)

    def test_a_completed_run_follows_its_file_results(self) -> None:
        """Partial success agrees with the card's pill for the same run."""
        cases = [
            (COMPLETED, 3, 0, "COMPLETED", RowStatus.SUCCESS),
            (COMPLETED, None, None, "COMPLETED", RowStatus.SUCCESS),
            (COMPLETED, 1, 2, "PARTIAL_SUCCESS", RowStatus.PARTIAL_SUCCESS),
            (COMPLETED, 0, 2, "COMPLETED", RowStatus.ERROR),
            (ERROR, 1, 2, "ERROR", RowStatus.ERROR),
        ]
        for run, successful, failed, pill, status in cases:
            with self.subTest(run=run, successful=successful, failed=failed):
                row = self._deployment(f"{run} {successful} {failed}")
                self._runs(row, [run], successful_files=successful, failed_files=failed)

                (latest,) = WorkflowExecution.get_last_run_statuses(row.pk)
                self.assertEqual(latest["status"], pill)
                self.assertEqual(self._status_of(row), status)

    def test_a_stopped_run_is_an_error(self) -> None:
        row = self._deployment("stopped")
        self._runs(row, [COMPLETED, STOPPED])

        self.assertEqual(self._status_of(row), RowStatus.ERROR)

    def test_inactive_wins_over_the_run(self) -> None:
        ran = self._deployment("ran", is_active=False)
        self._runs(ran, [COMPLETED])
        idle = self._deployment("idle", is_active=False)

        self.assertEqual(self._status_of(ran), RowStatus.INACTIVE)
        self.assertEqual(self._status_of(idle), RowStatus.INACTIVE)

    def test_counts_cover_every_row_once(self) -> None:
        self._runs(self._deployment("a"), [COMPLETED])
        self._runs(self._deployment("p"), [COMPLETED], successful_files=1, failed_files=1)
        self._runs(self._deployment("b"), [ERROR])
        self._runs(self._deployment("c"), [STOPPED])
        self._deployment("d")
        self._deployment("e", is_active=False)

        counts = count_by_status(APIDeployment.objects.all(), DEPLOYMENT_ROW_FIELDS)

        self.assertEqual(
            counts,
            StatusCounts(success=1, partial_success=1, error=2, never_run=1, inactive=1),
        )
        self.assertEqual(counts.total, APIDeployment.objects.count())


class FailingRuleTests(ListRowsSeed, TestCase):
    def _failing(self) -> list[Any]:
        summary = aggregate_rows(Pipeline.objects.all(), PIPELINE_ROW_FIELDS)
        return [streak.row for streak in summary.failing]

    def test_five_errors_in_a_row_is_failing_and_four_is_not(self) -> None:
        five = self._pipeline("five")
        self._runs(five, [COMPLETED, *FIVE_ERRORS])
        four = self._pipeline("four")
        self._runs(four, [COMPLETED, ERROR, ERROR, ERROR, ERROR])

        self.assertEqual(self._failing(), [five])

    def test_a_stopped_run_breaks_the_streak(self) -> None:
        """The failing rule is the dashboard's: only ERROR counts."""
        row = self._pipeline("stopped")
        self._runs(row, [ERROR, ERROR, ERROR, STOPPED, ERROR, ERROR, ERROR])

        self.assertEqual(self._failing(), [])

    def test_an_inactive_row_is_not_failing(self) -> None:
        self._runs(self._pipeline("paused", active=False), FIVE_ERRORS)

        self.assertEqual(self._failing(), [])

    def test_failing_rows_are_newest_failure_first_and_capped(self) -> None:
        older = self._pipeline("older")
        self._runs(older, FIVE_ERRORS, hours_ago=20)
        newer = self._pipeline("newer")
        self._runs(newer, FIVE_ERRORS, hours_ago=10)

        self.assertEqual(self._failing(), [newer, older])
        with mock.patch.object(list_aggregates, "FAILING_LIST_CAP", 1):
            summary = aggregate_rows(Pipeline.objects.all(), PIPELINE_ROW_FIELDS)
        self.assertEqual([s.row for s in summary.failing], [newer])
        self.assertEqual(summary.failing_count, 2)

    def test_rows_failing_at_the_same_time_are_in_descending_id_order(self) -> None:
        """Created in ascending id order, so a missing tie-break shows."""
        tied = [self._pipeline(f"tied {n}", id=uuid.UUID(int=n)) for n in (1, 2, 3)]
        for row in tied:
            self._runs(row, FIVE_ERRORS)

        self.assertEqual(self._failing(), tied[::-1])

    def test_the_failing_filter_matches_the_failing_count(self) -> None:
        self._runs(self._pipeline("broken"), FIVE_ERRORS)
        self._runs(self._pipeline("paused", active=False), FIVE_ERRORS)
        self._runs(self._pipeline("fine"), [COMPLETED])

        listed = apply_list_filters(
            Pipeline.objects.all(), ListFilters(failing=True), PIPELINE_ROW_FIELDS
        )
        summary = aggregate_rows(Pipeline.objects.all(), PIPELINE_ROW_FIELDS)

        self.assertEqual(
            [row.pipeline_name for row in listed],
            [s.row.pipeline_name for s in summary.failing],
        )


class ListFilterTests(ListRowsSeed, TestCase):
    def _names(self, filters: ListFilters) -> set[str]:
        rows = apply_list_filters(Pipeline.objects.all(), filters, PIPELINE_ROW_FIELDS)
        return {row.pipeline_name for row in rows}

    def test_no_filter_leaves_the_queryset_untouched(self) -> None:
        rows = Pipeline.objects.all()

        self.assertIs(apply_list_filters(rows, ListFilters(), PIPELINE_ROW_FIELDS), rows)

    def test_owner_matches_owners_and_co_owners_only(self) -> None:
        self._pipeline("mine")
        self._pipeline("shared", owner=self.coowner).grant_owner(self.owner)
        self._share(self._pipeline("theirs", owner=self.coowner), self.owner)

        self.assertEqual(self._names(ListFilters(owner=self.owner.id)), {"mine", "shared"})
        self.assertEqual(self._names(ListFilters(owner=self.viewer.id)), set())

    def test_last_run_bounds_are_inclusive(self) -> None:
        for name, hours in (("old", 30), ("mid", 20), ("new", 10)):
            self._pipeline(name, last_run_time=self.now - timedelta(hours=hours))
        self._pipeline("never")
        mid = self.now - timedelta(hours=20)

        self.assertEqual(self._names(ListFilters(last_run_after=mid)), {"mid", "new"})
        self.assertEqual(self._names(ListFilters(last_run_before=mid)), {"old", "mid"})
        self.assertEqual(
            self._names(ListFilters(last_run_after=mid, last_run_before=mid)), {"mid"}
        )

    def test_filters_combine(self) -> None:
        self._runs(self._pipeline("a", owner=self.coowner), [COMPLETED])
        self._runs(self._pipeline("b", owner=self.coowner), [ERROR])
        self._runs(self._pipeline("c"), [COMPLETED])

        filters = ListFilters(status=RowStatus.SUCCESS, owner=self.coowner.id)
        self.assertEqual(self._names(filters), {"a"})


class ListFilterParsingTests(SimpleTestCase):
    def test_blank_values_are_ignored(self) -> None:
        params = QueryDict("status=&owner=&last_run_after=&failing=")

        self.assertEqual(list_filters_from(params), ListFilters())

    def test_values_are_typed(self) -> None:
        params = QueryDict(
            "status=never_run&owner=7&failing=true&last_run_after=2026-10-01T00:00:00Z"
        )

        filters = list_filters_from(params)

        self.assertIs(filters.status, RowStatus.NEVER_RUN)
        self.assertEqual(filters.owner, 7)
        self.assertTrue(filters.failing)
        self.assertEqual(filters.last_run_after, datetime(2026, 10, 1, tzinfo=UTC))

    def test_a_bad_value_is_rejected_with_its_name(self) -> None:
        for query, name in (
            ("status=stopped", "status"),
            ("owner=abc", "owner"),
            ("owner=0", "owner"),
            ("last_run_before=yesterday", "last_run_before"),
            ("failing=maybe", "failing"),
        ):
            with self.subTest(query), self.assertRaises(ValidationError) as caught:
                list_filters_from(QueryDict(query))
            self.assertIn(name, caught.exception.detail)
