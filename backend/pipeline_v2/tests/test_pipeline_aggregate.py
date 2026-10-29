"""``pipeline/aggregate/``, the pipeline list it counts, and the status, owner,
last-run and failing list filters (UN-4320).
"""

from datetime import datetime, timedelta
from typing import Any
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone
from workflow_manager.workflow_v2.tests.list_rows import (
    COMPLETED,
    ERROR,
    FIVE_ERRORS,
    STOPPED,
    ListRowsSeed,
)

from pipeline_v2.models import Pipeline
from pipeline_v2.views import PipelineViewSet

URL = "/pipeline/"
ETL = "ETL"
TASK = "TASK"
FilterCases = dict[str, tuple[dict[str, Any], set[str]]]

# What a pipeline list row carried before the aggregate existed.
LIST_ROW_KEYS = {
    "access_control_bundle_id",
    "active",
    "api_endpoint",
    "app_icon",
    "app_id",
    "app_url",
    "co_owners_count",
    "created_at",
    "created_by",
    "created_by_email",
    "cron_string",
    "destination_instance_name",
    "destination_name",
    "id",
    "is_owner",
    "last_5_run_statuses",
    "last_run_status",
    "last_run_time",
    "modified_at",
    "modified_by",
    "next_run_time",
    "organization",
    "owner_emails",
    "pipeline_name",
    "pipeline_type",
    "run_count",
    "scheduled",
    "shared_groups",
    "shared_to_org",
    "source_instance_name",
    "source_name",
    "workflow",
    "workflow_id",
    "workflow_name",
}


class _PipelineRows(ListRowsSeed):
    def setUp(self) -> None:
        super().setUp()
        self.ok = self._row("nightly", ETL, 9, cron_string="0 0 * * *")
        self._runs(self.ok, [ERROR, COMPLETED], hours_ago=10)
        self._share(self.ok, self.viewer)
        self.broken = self._row(
            "hourly", ETL, 5, cron_string="30 * * * *", owner=self.coowner
        )
        self._runs(self.broken, [COMPLETED, *FIVE_ERRORS], hours_ago=10)
        self.stopped = self._row("sorter", TASK, 19)
        self._runs(self.stopped, [COMPLETED, STOPPED], hours_ago=20)
        self.fresh = self._row(
            "nightly draft", TASK, None, cron_string="", shared_to_org=True
        )
        self.paused = self._row("paused", ETL, 36, active=False)
        self._runs(self.paused, FIVE_ERRORS, hours_ago=40)
        self._runs(self._pipeline("elsewhere", org=self.org_b), FIVE_ERRORS)

    def _row(
        self, name: str, pipeline_type: str, ran_hours_ago: int | None, **fields: Any
    ) -> Pipeline:
        last_run = None
        if ran_hours_ago is not None:
            last_run = self.now - timedelta(hours=ran_hours_ago)
        return self._pipeline(name, pipeline_type, last_run_time=last_run, **fields)

    def _list(self, user: Any = None, **params: Any) -> Any:
        response = self._call(PipelineViewSet, "list", user or self.admin, URL, **params)
        assert response.status_code == 200, response.data
        return response.data

    def _aggregate(self, user: Any = None, **params: Any) -> Any:
        response = self._call(
            PipelineViewSet, "aggregate", user or self.admin, f"{URL}aggregate/", **params
        )
        assert response.status_code == 200, response.data
        return response.data

    def _names(self, **params: Any) -> set[str]:
        return {row["pipeline_name"] for row in self._list(**params)["results"]}


class PipelineListBaselineTests(_PipelineRows, TestCase):
    """The list as it was before the new filters, pinned."""

    def test_a_row_carries_the_same_keys(self) -> None:
        for row in self._list()["results"]:
            self.assertEqual(set(row), LIST_ROW_KEYS)

    def test_the_existing_filters_select_their_rows(self) -> None:
        cases: FilterCases = {
            "none": ({}, {"nightly", "hourly", "sorter", "nightly draft", "paused"}),
            "type": ({"type": TASK}, {"sorter", "nightly draft"}),
            "search": ({"search": "NIGHTLY"}, {"nightly", "nightly draft"}),
            "workflow": ({"workflow": str(self.ok.workflow_id)}, {"nightly"}),
            "pipeline_name": ({"pipeline_name": "nightly"}, {"nightly"}),
        }
        for label, (params, expected) in cases.items():
            with self.subTest(label):
                self.assertEqual(self._names(**params), expected)

    def test_the_next_run_is_listed_for_active_scheduled_rows_only(self) -> None:
        rows = {row["pipeline_name"]: row for row in self._list()["results"]}

        next_run = datetime.fromisoformat(rows["nightly"]["next_run_time"])
        self.assertGreater(next_run, timezone.now())
        self.assertEqual(rows["nightly"]["next_run_time"], next_run.isoformat())
        self.assertIsNone(rows["nightly draft"]["next_run_time"])
        self.assertIsNone(rows["paused"]["next_run_time"])

    def test_without_the_new_parameters_the_list_is_unchanged(self) -> None:
        """Same rows, same body and the same SQL as with the filtering removed."""

        def body_and_sql() -> tuple[Any, list[str]]:
            with CaptureQueriesContext(connection) as queries:
                body = self._list(type=ETL)
            return body, [query["sql"] for query in queries]

        body_and_sql()  # Warm the per-process caches both runs read.
        with mock.patch(
            "pipeline_v2.views.apply_list_filters", side_effect=lambda rows, *_: rows
        ):
            before = body_and_sql()

        self.assertEqual(body_and_sql(), before)


class PipelineAggregateTests(_PipelineRows, TestCase):
    def _filter_cases(self) -> list[dict[str, Any]]:
        after = (self.now - timedelta(hours=10)).isoformat()
        before = (self.now - timedelta(hours=8)).isoformat()
        return [
            {},
            {"type": ETL},
            {"type": TASK},
            {"search": "nightly"},
            {"workflow": str(self.ok.workflow_id)},
            {"pipeline_name": "hourly"},
            {"status": "success"},
            {"status": "error"},
            {"status": "never_run"},
            {"status": "inactive"},
            {"owner": self.coowner.id},
            {"last_run_after": after},
            {"last_run_before": before},
            {"failing": "true"},
            {"type": TASK, "status": "error"},
            {"type": ETL, "owner": self.owner.id, "last_run_before": before},
        ]

    def test_totals_equal_the_list_count_for_every_filter_and_caller(self) -> None:
        callers = (self.owner, self.coowner, self.viewer, self.outsider, self.admin)
        for user in callers:
            for params in self._filter_cases():
                with self.subTest(user=user.email, **params):
                    listed = self._list(user, **params)
                    summary = self._aggregate(user, **params)
                    self.assertEqual(summary["total"], listed["count"])
                    self.assertEqual(sum(summary["by_status"].values()), summary["total"])
                    failing = self._list(user, **{**params, "failing": "true"})
                    self.assertEqual(summary["failing_count"], failing["count"])

    def test_the_counts_follow_the_status_rule(self) -> None:
        summary = self._aggregate()

        self.assertEqual(summary["total"], 5)
        self.assertEqual(
            summary["by_status"],
            {"success": 1, "error": 2, "never_run": 1, "inactive": 1},
        )
        self.assertEqual(self._aggregate(type=TASK)["total"], 2)

    def test_not_scheduled_counts_active_rows_without_a_schedule(self) -> None:
        self.assertEqual(self._aggregate()["not_scheduled"], 2)
        self.assertEqual(self._aggregate(type=ETL)["not_scheduled"], 0)
        self.assertEqual(self._aggregate(self.outsider)["not_scheduled"], 1)

    def test_a_failing_row_names_its_type_and_next_run(self) -> None:
        summary = self._aggregate()

        self.assertEqual(summary["failing_count"], 1)
        (row,) = summary["failing"]
        self.assertEqual(row["id"], str(self.broken.pk))
        self.assertEqual(row["name"], "hourly")
        self.assertEqual(row["pipeline_type"], ETL)
        self.assertEqual(row["owner_email"], self.coowner.email)
        self.assertEqual(row["failures_in_a_row"], 5)
        self.assertGreater(
            datetime.fromisoformat(row["next_run_time"]), timezone.now()
        )

    def test_each_list_filter_selects_its_rows(self) -> None:
        cases: FilterCases = {
            "status=success": ({"status": "success"}, {"nightly"}),
            "status=error": ({"status": "error"}, {"hourly", "sorter"}),
            "status=never_run": ({"status": "never_run"}, {"nightly draft"}),
            "status=inactive": ({"status": "inactive"}, {"paused"}),
            "owner": ({"owner": self.coowner.id}, {"hourly"}),
            "failing": ({"failing": "true"}, {"hourly"}),
            "last_run_after": (
                {"last_run_after": (self.now - timedelta(hours=9)).isoformat()},
                {"nightly", "hourly"},
            ),
            "last_run_before": (
                {"last_run_before": (self.now - timedelta(hours=19)).isoformat()},
                {"sorter", "paused"},
            ),
            "combined": ({"type": TASK, "status": "error"}, {"sorter"}),
        }
        for label, (params, expected) in cases.items():
            with self.subTest(label):
                self.assertEqual(self._names(**params), expected)

    def test_a_malformed_parameter_is_a_bad_request(self) -> None:
        for params in ({"status": "stopped"}, {"owner": "-1"}, {"failing": "maybe"}):
            for action in ("list", "aggregate"):
                with self.subTest(action=action, **params):
                    response = self._call(
                        PipelineViewSet, action, self.admin, URL, **params
                    )
                    self.assertEqual(response.status_code, 400)

    def test_the_query_count_does_not_grow_with_the_rows(self) -> None:
        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                self._aggregate()
            return len(captured)

        queries()  # Warm the per-process caches both runs read.
        few = queries()
        for n in range(9):
            row = self._pipeline(f"more {n}", owner=self.coowner, cron_string="0 * * * *")
            self._runs(row, FIVE_ERRORS if n % 2 else [COMPLETED])

        self.assertEqual(queries(), few)

    def test_the_route_is_not_taken_for_a_pipeline_id(self) -> None:
        match = resolve(reverse("tenant:pipeline-aggregate"))

        self.assertIs(match.func.cls, PipelineViewSet)
        self.assertEqual(match.func.actions["get"], "aggregate")


class NextRunTimeTests(ListRowsSeed, TestCase):
    def test_no_next_run_without_an_active_schedule(self) -> None:
        self.assertIsNone(self._pipeline("blank", cron_string="").next_run_time())
        idle = self._pipeline("idle", cron_string="0 0 * * *", active=False)
        self.assertIsNone(idle.next_run_time())

    def test_an_unreadable_schedule_has_no_next_run(self) -> None:
        row = self._pipeline("broken", cron_string="not a cron")

        with self.assertNoLogs("pipeline_v2.models", level="WARNING"):
            self.assertIsNone(row.next_run_time())
