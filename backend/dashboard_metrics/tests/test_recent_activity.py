"""``metrics/recent-activity/``: the paged form with counts (DG-02) and the
per-row ``surface`` (DG-03), and the default form left exactly as it was.

DB-backed Django ``TestCase`` → auto-marked ``integration`` by ``backend/conftest.py``.
"""

import json
import uuid
from datetime import timedelta

from account_v2.models import Organization
from api_v2.models import APIDeployment
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from permissions.tests.base import CoOwnerOrgTestMixin
from pipeline_v2.models import Pipeline
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory, force_authenticate
from usage_v2.models import Usage, UsageType
from utils.user_context import UserContext
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics import urls
from dashboard_metrics.views import DashboardMetricsViewSet

COMPLETED = ExecutionStatus.COMPLETED.value
ERROR = ExecutionStatus.ERROR.value
EXECUTING = ExecutionStatus.EXECUTING.value
ALL_STATUSES = [s.value for s in ExecutionStatus]


class _Seed(CoOwnerOrgTestMixin):
    def setUp(self) -> None:
        self._seed_org()
        self.now = timezone.now().replace(microsecond=0)

    def _workflow(self, org: Organization | None = None) -> Workflow:
        return Workflow.objects.create(
            workflow_name=f"wf-{uuid.uuid4().hex[:6]}",
            organization=org or self.org,
            created_by=self.owner,
        )

    def _pipeline(self, pipeline_type: str) -> Pipeline:
        return Pipeline.objects.create(
            pipeline_name=f"{pipeline_type.lower()}-{uuid.uuid4().hex[:6]}",
            pipeline_type=pipeline_type,
            workflow=self._workflow(),
            organization=self.org,
            created_by=self.owner,
        )

    def _deployment(self) -> APIDeployment:
        return APIDeployment.objects.create(
            api_name=f"api-{uuid.uuid4().hex[:6]}",
            display_name="api",
            workflow=self._workflow(),
            organization=self.org,
            created_by=self.owner,
        )

    def _file(
        self,
        source,
        status: str,
        hours_ago: float,
        workflow: Workflow | None = None,
        tokens: int = 0,
    ) -> WorkflowFileExecution:
        """One file execution, from ``source`` (a pipeline or deployment, or
        None for a manual workflow run), created ``hours_ago``."""
        execution = WorkflowExecution.objects.create(
            workflow=workflow or source.workflow,
            pipeline_id=source.pk if source is not None else None,
            status=status,
        )
        file_execution = WorkflowFileExecution.objects.create(
            workflow_execution=execution,
            file_name=f"{uuid.uuid4().hex[:6]}.pdf",
            status=status,
            execution_time=1.5,
        )
        WorkflowFileExecution.objects.filter(pk=file_execution.pk).update(
            created_at=self.now - timedelta(hours=hours_ago)
        )
        file_execution.refresh_from_db()
        if tokens:
            Usage.objects.create(
                organization=self.org,
                run_id=file_execution.pk,
                adapter_instance_id=str(uuid.uuid4()),
                usage_type=UsageType.LLM,
                model_name="gpt-4o-mini",
                embedding_tokens=0,
                prompt_tokens=tokens,
                completion_tokens=tokens,
                total_tokens=tokens * 2,
                cost_in_dollars=0.25,
            )
        return file_execution

    def _get(self, **params):
        # refresh=true skips the response cache, which would otherwise answer a
        # repeated query from an earlier test step. It is not a paged-form param.
        params.setdefault("refresh", "true")
        request = APIRequestFactory().get("/metrics/recent-activity/", params)
        force_authenticate(request, user=self.owner)
        return DashboardMetricsViewSet.as_view({"get": "recent_activity"})(request)

    def _ids(self, response) -> list[str]:
        return [row["id"] for row in response.data["activity"]]


class DefaultFormTests(_Seed, TestCase):
    """No new parameter: the response is the original one, byte for byte."""

    def test_default_response_is_unchanged(self) -> None:
        etl, task, api = (
            self._pipeline("ETL"),
            self._pipeline("TASK"),
            self._deployment(),
        )
        manual = self._workflow()
        e = self._file(etl, COMPLETED, 1, tokens=10)
        t = self._file(task, ERROR, 2)
        a = self._file(api, COMPLETED, 3)
        m = self._file(None, EXECUTING, 4, workflow=manual)

        def row(fe, type_, tokens=0, cost=0):
            # The original key order, which JSON clients see.
            return {
                "id": str(fe.pk),
                "execution_id": str(fe.workflow_execution_id),
                "type": type_,
                "file_name": fe.file_name,
                "status": fe.status,
                "workflow_name": fe.workflow_execution.workflow.workflow_name,
                "created_at": fe.created_at.isoformat(),
                "execution_time": 1.5,
                "total_tokens": tokens,
                "cost": cost,
            }

        expected = {
            "activity": [
                row(e, "etl", tokens=20, cost=0.25),
                # A Task pipeline run stays "workflow" here; only `surface` differs.
                row(t, "workflow"),
                row(a, "api"),
                row(m, "workflow"),
            ]
        }
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            JSONRenderer().render(response.data), JSONRenderer().render(expected)
        )

    def test_limit_still_applies_and_adds_nothing(self) -> None:
        etl = self._pipeline("ETL")
        for hours in range(1, 4):
            self._file(etl, COMPLETED, hours)

        response = self._get(limit="2")
        self.assertEqual(list(response.data), ["activity"])
        self.assertEqual(len(response.data["activity"]), 2)
        self.assertNotIn("surface", response.data["activity"][0])
        # The old cap and fallback are kept.
        self.assertEqual(len(self._get(limit="500").data["activity"]), 3)
        self.assertEqual(len(self._get(limit="x").data["activity"]), 3)


class PagedFormTests(_Seed, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.etl = self._pipeline("ETL")
        self.task = self._pipeline("TASK")
        self.default = self._pipeline("DEFAULT")
        self.api = self._deployment()
        self.manual = self._workflow()
        # Newest first: hours ago 1..7.
        self.rows = {
            "etl_ok": self._file(self.etl, COMPLETED, 1),
            "task_err": self._file(self.task, ERROR, 2),
            "api_ok": self._file(self.api, COMPLETED, 3),
            "manual_err": self._file(None, ERROR, 4, workflow=self.manual),
            "default_ok": self._file(self.default, COMPLETED, 5),
            "etl_running": self._file(self.etl, EXECUTING, 6),
            # Outside a 2-day range.
            "etl_old": self._file(self.etl, ERROR, 24 * 3),
        }

    def _range(self, days: int = 2) -> dict:
        return {
            "start_date": (self.now - timedelta(days=days)).isoformat(),
            "end_date": self.now.isoformat(),
        }

    def _expect_ids(self, *names: str) -> list[str]:
        return [str(self.rows[n].pk) for n in names]

    def test_any_new_param_switches_to_the_paged_form(self) -> None:
        for param, value in (
            ("start_date", (self.now - timedelta(days=2)).isoformat()),
            ("end_date", self.now.isoformat()),
            ("status", COMPLETED),
            ("surface", "etl"),
            ("page", "1"),
            ("page_size", "5"),
        ):
            with self.subTest(param):
                response = self._get(**{param: value})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(
                    set(response.data),
                    {
                        "activity",
                        "count",
                        "status_counts",
                        "page",
                        "page_size",
                        "start_date",
                        "end_date",
                    },
                )
                self.assertIn("surface", response.data["activity"][0])

    def test_range_counts_and_surface(self) -> None:
        response = self._get(**self._range())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._ids(response),
            self._expect_ids(
                "etl_ok",
                "task_err",
                "api_ok",
                "manual_err",
                "default_ok",
                "etl_running",
            ),
        )
        self.assertEqual(response.data["count"], 6)
        self.assertEqual(
            response.data["status_counts"],
            {
                "PENDING": 0,
                "EXECUTING": 1,
                "COMPLETED": 3,
                "STOPPED": 0,
                "ERROR": 2,
            },
        )
        self.assertEqual((response.data["page"], response.data["page_size"]), (1, 20))
        self.assertEqual(
            [(row["type"], row["surface"]) for row in response.data["activity"]],
            [
                ("etl", "etl"),
                ("workflow", "task"),
                ("api", "api"),
                ("workflow", "workflow"),
                ("workflow", "workflow"),
                ("etl", "etl"),
            ],
        )

    def test_range_defaults_to_the_last_30_days(self) -> None:
        old = self._file(self.etl, COMPLETED, 24 * 31)
        response = self._get(page="1")
        self.assertNotIn(str(old.pk), self._ids(response))
        self.assertIn(str(self.rows["etl_old"].pk), self._ids(response))
        self.assertEqual(response.data["count"], 7)

    def test_status_filter_narrows_rows_and_count_not_status_counts(self) -> None:
        response = self._get(status="error,STOPPED", **self._range())
        self.assertEqual(self._ids(response), self._expect_ids("task_err", "manual_err"))
        self.assertEqual(response.data["count"], 2)
        # Chip counts stay those of the whole range.
        self.assertEqual(response.data["status_counts"]["COMPLETED"], 3)
        self.assertEqual(sum(response.data["status_counts"].values()), 6)

    def test_surface_filter(self) -> None:
        cases = {
            "etl": ["etl_ok", "etl_running"],
            "task": ["task_err"],
            "api": ["api_ok"],
            "workflow": ["manual_err", "default_ok"],
            "task,api": ["task_err", "api_ok"],
            "etl,task,api,workflow": [
                "etl_ok",
                "task_err",
                "api_ok",
                "manual_err",
                "default_ok",
                "etl_running",
            ],
        }
        for surface, names in cases.items():
            with self.subTest(surface):
                response = self._get(surface=surface, **self._range())
                self.assertEqual(self._ids(response), self._expect_ids(*names))
                self.assertEqual(response.data["count"], len(names))
                self.assertEqual(
                    sum(response.data["status_counts"].values()), len(names)
                )

    def test_surface_and_status_together(self) -> None:
        response = self._get(surface="workflow", status=ERROR, **self._range())
        self.assertEqual(self._ids(response), self._expect_ids("manual_err"))
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["status_counts"]["COMPLETED"], 1
        )  # default_ok

    def test_paging(self) -> None:
        all_ids = self._expect_ids(
            "etl_ok", "task_err", "api_ok", "manual_err", "default_ok", "etl_running"
        )
        pages = [
            self._ids(self._get(page=str(p), page_size="4", **self._range()))
            for p in (1, 2, 3)
        ]
        self.assertEqual(pages, [all_ids[:4], all_ids[4:], []])

    def test_paging_is_stable_when_created_at_ties(self) -> None:
        tied = [self._file(self.etl, COMPLETED, 0.5) for _ in range(4)]
        WorkflowFileExecution.objects.filter(pk__in=[t.pk for t in tied]).update(
            created_at=self.now - timedelta(minutes=30)
        )
        seen = []
        for page in (1, 2):
            seen += self._ids(self._get(page=str(page), page_size="2", surface="etl"))
        self.assertCountEqual(seen, [str(t.pk) for t in tied])

    def test_empty_range(self) -> None:
        response = self._get(
            start_date=(self.now + timedelta(days=1)).isoformat(),
            end_date=(self.now + timedelta(days=2)).isoformat(),
        )
        self.assertEqual(response.data["activity"], [])
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["status_counts"], dict.fromkeys(ALL_STATUSES, 0))

    def test_other_organisations_are_not_counted(self) -> None:
        other = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        execution = WorkflowExecution.objects.create(
            workflow=self._workflow(org=other), status=ERROR
        )
        file_execution = WorkflowFileExecution.objects.create(
            workflow_execution=execution, file_name="b.pdf", status=ERROR
        )
        WorkflowFileExecution.objects.filter(pk=file_execution.pk).update(
            created_at=self.now - timedelta(hours=1)
        )
        response = self._get(**self._range())
        self.assertEqual(response.data["count"], 6)
        self.assertEqual(response.data["status_counts"]["ERROR"], 2)

    def test_invalid_params_are_rejected(self) -> None:
        cases = {
            "status": {"status": "FAILED"},
            "empty status": {"status": ","},
            "surface": {"surface": "pipeline"},
            "page": {"page": "0"},
            "page_size": {"page_size": "101"},
            "date": {"start_date": "yesterday"},
            "order": {
                "start_date": self.now.isoformat(),
                "end_date": (self.now - timedelta(days=1)).isoformat(),
            },
            "too long": {
                "start_date": (self.now - timedelta(days=400)).isoformat(),
                "end_date": self.now.isoformat(),
            },
        }
        for name, params in cases.items():
            with self.subTest(name):
                self.assertEqual(self._get(**params).status_code, 400)

    def test_no_organization_is_forbidden(self) -> None:
        UserContext.set_organization_identifier(None)
        self.assertEqual(self._get(page="1").status_code, 403)


class ContractTests(SimpleTestCase):
    """The drf-spectacular annotation is the published contract, with the README."""

    def test_schema_documents_both_forms(self) -> None:
        schema = SchemaGenerator(patterns=urls.urlpatterns).get_schema(
            request=None, public=True
        )
        (operation,) = (
            op
            for path in schema["paths"].values()
            for op in path.values()
            if op.get("operationId") == "metrics_recent_activity"
        )
        self.assertEqual(
            {p["name"] for p in operation["parameters"]},
            {
                "limit",
                "refresh",
                "start_date",
                "end_date",
                "status",
                "surface",
                "page",
                "page_size",
            },
        )
        components = schema["components"]["schemas"]
        self.assertLessEqual(
            {"activity", "count", "status_counts", "page", "page_size"},
            set(components["RecentActivityResponse"]["properties"]),
        )
        row = components["RecentActivityRow"]
        self.assertIn("surface", row["properties"])
        self.assertNotIn("surface", row["required"])
        # Round-trips as JSON, as the published schema must.
        json.dumps(schema, default=str)
