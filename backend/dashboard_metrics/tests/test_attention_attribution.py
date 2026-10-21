"""Dashboard attention feed and failure attribution (PB-T14).

* Each OSS attention kind appears with seeded data, and only when the row's
  last five finished runs all ended in ERROR, the latest within the range.
* Attribution per day and per source sums to the ``failed_pages`` metric for
  the same range.
* Both responses validate against the committed JSON Schemas.

DB-backed Django ``TestCase`` → auto-marked ``integration`` by ``backend/conftest.py``.
"""

import json
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import mock

import jsonschema
from account_usage.models import PageUsage
from account_v2.models import Organization
from api_v2.models import APIDeployment
from django.test import TestCase
from django.utils import timezone
from permissions.tests.base import CoOwnerOrgTestMixin
from pipeline_v2.models import Pipeline
from rest_framework.test import APIRequestFactory, force_authenticate
from utils.user_context import UserContext
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.failing_streaks import failing_streaks
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics import attention
from dashboard_metrics.attention import (
    AttentionItem,
    AttentionProvider,
    FailingPipelineProvider,
    get_attention_providers,
    register_attention_provider,
)
from dashboard_metrics.models import Granularity
from dashboard_metrics.services import MetricsQueryService
from dashboard_metrics.views import DashboardMetricsViewSet

CONTRACT = Path(__file__).parents[1] / "contract"
ATTENTION_SCHEMA = json.loads((CONTRACT / "attention-response.schema.json").read_text())
ATTRIBUTION_SCHEMA = json.loads(
    (CONTRACT / "attribution-response.schema.json").read_text()
)

ERROR = ExecutionStatus.ERROR.value
COMPLETED = ExecutionStatus.COMPLETED.value
STOPPED = ExecutionStatus.STOPPED.value
FORMATS = jsonschema.FormatChecker()


class _Seed(CoOwnerOrgTestMixin):
    def setUp(self) -> None:
        self._seed_org()
        self.now = timezone.now().replace(microsecond=0)

    def _workflow(self, org: Organization | None = None, name: str = "wf") -> Workflow:
        return Workflow.objects.create(
            workflow_name=f"{name}-{uuid.uuid4().hex[:6]}",
            organization=org or self.org,
            created_by=self.owner,
        )

    def _pipeline(self, name: str, pipeline_type: str = "ETL", **fields) -> Pipeline:
        return Pipeline.objects.create(
            pipeline_name=name,
            pipeline_type=pipeline_type,
            workflow=self._workflow(),
            organization=self.org,
            created_by=self.owner,
            active=fields.pop("active", True),
            **fields,
        )

    def _deployment(self, name: str, **fields) -> APIDeployment:
        return APIDeployment.objects.create(
            api_name=f"api-{uuid.uuid4().hex[:6]}",
            display_name=name,
            workflow=self._workflow(),
            organization=self.org,
            created_by=self.owner,
            **fields,
        )

    def _run(
        self, row, status: str, hours_ago: float, workflow=None
    ) -> WorkflowExecution:
        execution = WorkflowExecution.objects.create(
            workflow=workflow or row.workflow,
            pipeline_id=row.pk if row is not None else None,
            status=status,
        )
        WorkflowExecution.objects.filter(pk=execution.pk).update(
            created_at=self.now - timedelta(hours=hours_ago)
        )
        return execution

    def _runs(self, row, statuses_oldest_first: list[str], start_hours_ago: int = 10):
        for i, status in enumerate(statuses_oldest_first):
            self._run(row, status, start_hours_ago - i)

    def _get(self, action: str, **params):
        request = APIRequestFactory().get(f"/metrics/{action}/", params)
        force_authenticate(request, user=self.owner)
        return DashboardMetricsViewSet.as_view({"get": action})(request)


class FailingStreakTests(_Seed, TestCase):
    def test_five_failures_after_a_success_is_failing(self) -> None:
        pipeline = self._pipeline("nightly")
        self._runs(pipeline, [COMPLETED, ERROR, ERROR, ERROR, ERROR, ERROR, ERROR])

        (streak,) = failing_streaks(Pipeline.objects.all())
        self.assertEqual(streak.row, pipeline)
        # The streak counts every failure since the success, not just five.
        self.assertEqual(streak.failures_in_a_row, 6)
        self.assertEqual(streak.last_success, self.now - timedelta(hours=10))
        self.assertEqual(streak.failing_since, self.now - timedelta(hours=9))
        self.assertEqual(streak.last_failure, self.now - timedelta(hours=4))

    def test_never_succeeded_counts_every_failure(self) -> None:
        pipeline = self._pipeline("new")
        self._runs(pipeline, [ERROR] * 5)

        (streak,) = failing_streaks(Pipeline.objects.all())
        self.assertIsNone(streak.last_success)
        self.assertEqual(streak.failures_in_a_row, 5)
        self.assertEqual(streak.failing_since, self.now - timedelta(hours=10))

    def test_streak_starts_after_the_last_run_that_did_not_fail(self) -> None:
        cases = {
            "errors before the last success": [ERROR, ERROR, COMPLETED],
            "a stop": [COMPLETED, ERROR, STOPPED],
        }
        for name, before in cases.items():
            with self.subTest(name):
                pipeline = self._pipeline(name)
                self._runs(pipeline, before + [ERROR] * 5)
                (streak,) = (
                    s
                    for s in failing_streaks(Pipeline.objects.all())
                    if s.row == pipeline
                )
                self.assertEqual(streak.failures_in_a_row, 5)
                self.assertEqual(streak.failing_since, self.now - timedelta(hours=7))

    def test_unfinished_runs_are_skipped(self) -> None:
        pipeline = self._pipeline("retrying")
        self._runs(pipeline, [ERROR] * 5 + ["PENDING", "EXECUTING"])

        (streak,) = failing_streaks(Pipeline.objects.all())
        self.assertEqual(streak.failures_in_a_row, 5)
        self.assertEqual(streak.last_failure, self.now - timedelta(hours=6))

    def test_range_bounds_the_latest_failure(self) -> None:
        pipeline = self._pipeline("nightly")
        self._runs(pipeline, [ERROR] * 5)  # latest failure 6 hours ago
        hours = lambda h: self.now - timedelta(hours=h)  # noqa: E731
        cases = {
            "inside": (hours(7), hours(5), [pipeline]),
            "start after it": (hours(5), None, []),
            "end before it": (None, hours(7), []),
        }
        for name, (start, end, expected) in cases.items():
            with self.subTest(name):
                rows = [
                    s.row for s in failing_streaks(Pipeline.objects.all(), start, end)
                ]
                self.assertEqual(rows, expected)

    def test_not_failing(self) -> None:
        cases = {
            "four failures": [ERROR] * 4,
            "a success among the last five": [ERROR, ERROR, COMPLETED, ERROR, ERROR],
            "a stop among the last five": [ERROR, ERROR, STOPPED, ERROR, ERROR],
        }
        for name, statuses in cases.items():
            with self.subTest(name):
                self._runs(self._pipeline(name), statuses)
        self.assertEqual(failing_streaks(Pipeline.objects.all()), [])

    def test_one_query_whatever_the_number_of_rows(self) -> None:
        for i in range(3):
            self._runs(self._pipeline(f"p{i}"), [ERROR] * 5)
        with self.assertNumQueries(1):
            self.assertEqual(len(failing_streaks(Pipeline._base_manager.all())), 3)


class AttentionTests(_Seed, TestCase):
    def test_failing_pipeline_and_deployment_items(self) -> None:
        etl = self._pipeline("nightly-etl")
        self._runs(etl, [COMPLETED] + [ERROR] * 5)
        task = self._pipeline("cleanup", pipeline_type="TASK")
        self._runs(task, [ERROR] * 5, start_hours_ago=20)
        deployment = self._deployment("Invoices API")
        # The newest failure of all, yet listed after the pipelines.
        self._runs(deployment, [ERROR] * 5, start_hours_ago=8)

        response = self._get("attention")
        self.assertEqual(response.status_code, 200)
        jsonschema.validate(response.data, ATTENTION_SCHEMA, format_checker=FORMATS)
        self.assertEqual(response.data["failed_kinds"], [])
        by_id = {item["id"]: item for item in response.data["items"]}

        self.assertEqual(
            by_id[str(etl.pk)],
            {
                "kind": "failing_pipeline",
                "id": str(etl.pk),
                "name": "nightly-etl",
                "count": 5,
                "since": (self.now - timedelta(hours=9)).isoformat(),
                "route": {"key": "etl_pipeline.detail", "params": {"id": str(etl.pk)}},
                "details": {
                    "last_failure": (self.now - timedelta(hours=5)).isoformat(),
                    "last_success": (self.now - timedelta(hours=10)).isoformat(),
                    "pipeline_type": "ETL",
                },
            },
        )
        self.assertEqual(by_id[str(task.pk)]["route"]["key"], "task_pipeline.detail")
        self.assertEqual(by_id[str(deployment.pk)]["kind"], "failing_deployment")
        self.assertEqual(by_id[str(deployment.pk)]["name"], "Invoices API")
        self.assertEqual(
            by_id[str(deployment.pk)]["route"]["key"], "api_deployment.detail"
        )
        # Pipelines first, then deployments; newest failure first within a kind.
        self.assertEqual(
            [i["id"] for i in response.data["items"]],
            [str(etl.pk), str(task.pk), str(deployment.pk)],
        )

    def test_excluded_rows(self) -> None:
        self._runs(self._pipeline("paused", active=False), [ERROR] * 5)
        self._runs(self._deployment("off", is_active=False), [ERROR] * 5)
        # Failing, but its last failure is before the range.
        self._runs(self._pipeline("old"), [ERROR] * 5, start_hours_ago=24 * 40)

        other = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        foreign = Pipeline.objects.create(
            pipeline_name="foreign",
            workflow=self._workflow(other),
            organization=other,
            created_by=self.owner,
            active=True,
        )
        self._runs(foreign, [ERROR] * 5)

        response = self._get("attention")
        self.assertEqual(response.data["items"], [])

    def test_range_follows_the_query_parameters(self) -> None:
        pipeline = self._pipeline("nightly")
        self._runs(pipeline, [ERROR] * 5, start_hours_ago=24 * 40)
        start = (self.now - timedelta(days=60)).isoformat()

        response = self._get("attention", start_date=start)
        self.assertEqual([i["id"] for i in response.data["items"]], [str(pipeline.pk)])


class _Reviews(AttentionProvider):
    kind = "test_reviews"
    order = 30

    def items(self, organization, start_date, end_date):
        return [
            AttentionItem(
                kind=self.kind,
                id="test_reviews",
                name=None,
                count=4,
                since=start_date,
            )
        ]


class _Broken(AttentionProvider):
    kind = "test_broken"
    order = 40

    def items(self, organization, start_date, end_date):
        raise RuntimeError("source unavailable")


class _Malformed(AttentionProvider):
    kind = "test_malformed"
    order = 50

    def items(self, organization, start_date, end_date):
        return [AttentionItem(kind=self.kind, id="x", name=None, count=1, since="now")]


class _First(AttentionProvider):
    kind = "test_first"
    order = 5

    def items(self, organization, start_date, end_date):
        return []


class AttentionProviderRegistryTests(_Seed, TestCase):
    """Test-only kinds on a copy of the registry, restored after each test."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.dict(attention._providers)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Registered out of order: _First sorts before the OSS providers.
        for provider in (_Broken(), _Reviews(), _Malformed(), _First()):
            register_attention_provider(provider)

    def test_contributed_kinds_and_failures(self) -> None:
        response = self._get("attention")
        jsonschema.validate(response.data, ATTENTION_SCHEMA, format_checker=FORMATS)
        (item,) = response.data["items"]
        self.assertEqual(
            (item["kind"], item["count"], item["route"]), ("test_reviews", 4, None)
        )
        # A provider that raises, or returns an item that cannot be serialized,
        # is named, never shown as "nothing needs attention".
        self.assertEqual(response.data["failed_kinds"], ["test_broken", "test_malformed"])

    def test_malformed_items_are_refused(self) -> None:
        good = {"kind": "test_reviews", "id": "x", "name": None, "since": None}
        cases = {
            "another kind": {**good, "kind": "test_broken", "count": 1},
            "negative count": {**good, "count": -1},
            "bool count": {**good, "count": True},
            "since not a datetime": {**good, "count": 1, "since": "now"},
            "since a date": {**good, "count": 1, "since": self.now.date()},
            "id not a string": {**good, "count": 1, "id": 7},
            "name not a string": {**good, "count": 1, "name": 7},
            "since without a timezone": {
                **good,
                "count": 1,
                "since": self.now.replace(tzinfo=None),
            },
            "bad route key": {**good, "count": 1, "route_key": "Detail"},
            "route param not a string": {
                **good,
                "count": 1,
                "route_key": "x.detail",
                "route_params": {"id": 7},
            },
            "details not a dict": {**good, "count": 1, "details": []},
            "details not renderable": {**good, "count": 1, "details": {"x": object()}},
        }
        for name, fields in cases.items():
            with self.subTest(name), self.assertRaises((ValueError, TypeError)):
                attention._serialize(_Reviews(), AttentionItem(**fields))
        self.assertEqual(
            attention._serialize(_Reviews(), AttentionItem(**good, count=0))["count"], 0
        )

    def test_display_order(self) -> None:
        kinds = [p.kind for p in get_attention_providers()]
        self.assertEqual(kinds[0], "test_first")
        self.assertLess(
            kinds.index("failing_pipeline"), kinds.index("failing_deployment")
        )
        self.assertLess(kinds.index("failing_deployment"), kinds.index("test_reviews"))
        self.assertLess(kinds.index("test_reviews"), kinds.index("test_broken"))

    def test_registration_rules(self) -> None:
        register_attention_provider(_Reviews())  # same class again: no-op

        class _Other(_Reviews):
            pass

        with self.assertRaisesRegex(ValueError, "already registered"):
            register_attention_provider(_Other())

        class _BadKind(_Reviews):
            kind = "Test-Reviews"

        with self.assertRaisesRegex(ValueError, "Invalid attention kind"):
            register_attention_provider(_BadKind())

        class _BadOrder(_Reviews):
            kind = "test_bad_order"
            order = "30"

        with self.assertRaisesRegex(ValueError, "needs an int order"):
            register_attention_provider(_BadOrder())

    def test_oss_providers_are_registered_by_the_app(self) -> None:
        kinds = {p.kind for p in get_attention_providers()}
        self.assertIn(FailingPipelineProvider.kind, kinds)


class AttributionTests(_Seed, TestCase):
    def _failed_file(self, execution, pages: int, days_ago: int, status=ERROR) -> None:
        file_execution = WorkflowFileExecution.objects.create(
            workflow_execution=execution,
            file_name=f"{uuid.uuid4().hex[:6]}.pdf",
            status=status,
        )
        WorkflowFileExecution.objects.filter(pk=file_execution.pk).update(
            created_at=self.now - timedelta(days=days_ago)
        )
        PageUsage.objects.create(
            organization_id=self.org.organization_id,
            file_name=file_execution.file_name,
            file_type="application/pdf",
            run_id=str(file_execution.pk),
            pages_processed=pages,
            file_size=1024,
        )

    def _seed(self) -> dict:
        etl = self._pipeline("nightly-etl")
        deployment = self._deployment("Invoices API")
        manual = self._workflow(name="manual")
        gone = self._pipeline("removed")

        etl_run = self._run(etl, ERROR, 1)
        api_run = self._run(deployment, COMPLETED, 1)
        manual_run = self._run(None, ERROR, 1, workflow=manual)
        gone_run = self._run(gone, ERROR, 1)

        self._failed_file(etl_run, 30, days_ago=2)
        self._failed_file(etl_run, 20, days_ago=1)
        self._failed_file(api_run, 10, days_ago=1)
        self._failed_file(api_run, 99, days_ago=1, status=COMPLETED)  # not a failure
        self._failed_file(manual_run, 5, days_ago=2)
        self._failed_file(gone_run, 1, days_ago=1)
        gone_id = str(gone.pk)
        Pipeline.objects.filter(pk=gone.pk).delete()

        other = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        foreign_run = WorkflowExecution.objects.create(
            workflow=self._workflow(other), status=ERROR
        )
        self._failed_file(foreign_run, 500, days_ago=1)
        return {
            "etl": str(etl.pk),
            "api": str(deployment.pk),
            "manual": str(manual.pk),
            "gone": gone_id,
        }

    def test_breakdown_by_source_and_day(self) -> None:
        ids = self._seed()
        response = self._get("attribution")
        self.assertEqual(response.status_code, 200)
        jsonschema.validate(response.data, ATTRIBUTION_SCHEMA, format_checker=FORMATS)
        data = response.data

        self.assertEqual(data["total_failed_pages"], 66)
        self.assertEqual(
            [(s["id"], s["name"], s["type"], s["failed_pages"]) for s in data["sources"]],
            [
                (ids["etl"], "nightly-etl", "etl_pipeline", 50),
                (ids["api"], "Invoices API", "api_deployment", 10),
                (
                    ids["manual"],
                    Workflow.objects.get(pk=ids["manual"]).workflow_name,
                    "workflow",
                    5,
                ),
                (ids["gone"], None, "deleted", 1),
            ],
        )
        self.assertAlmostEqual(sum(s["share"] for s in data["sources"]), 1.0, places=3)
        self.assertEqual(data["sources"][0]["share"], round(50 / 66, 4))

        two_days_ago = (self.now - timedelta(days=2)).date().isoformat()
        by_day = {d["date"]: d for d in data["days"]}
        self.assertEqual(by_day[two_days_ago]["failed_pages"], 35)
        self.assertEqual(
            by_day[two_days_ago]["sources"],
            [
                {"id": ids["etl"], "failed_pages": 30},
                {"id": ids["manual"], "failed_pages": 5},
            ],
        )

    def test_totals_equal_the_failed_pages_series(self) -> None:
        self._seed()
        start = self.now - timedelta(days=30)
        series = MetricsQueryService.get_failed_pages(
            str(self.org.id), start, self.now, Granularity.DAY
        )
        response = self._get(
            "attribution", start_date=start.isoformat(), end_date=self.now.isoformat()
        )

        self.assertEqual(
            response.data["total_failed_pages"], sum(r["value"] for r in series)
        )
        self.assertEqual(
            {d["date"]: d["failed_pages"] for d in response.data["days"]},
            {r["period"].date().isoformat(): r["value"] for r in series},
        )

    def test_empty_range(self) -> None:
        response = self._get("attribution")
        jsonschema.validate(response.data, ATTRIBUTION_SCHEMA, format_checker=FORMATS)
        self.assertEqual(
            (
                response.data["total_failed_pages"],
                response.data["sources"],
                response.data["days"],
            ),
            (0, [], []),
        )


class OrganizationContextTests(_Seed, TestCase):
    def test_no_organization_is_forbidden(self) -> None:
        UserContext.set_organization_identifier(None)
        for action in ("attention", "attribution"):
            with self.subTest(action):
                self.assertEqual(self._get(action).status_code, 403)
