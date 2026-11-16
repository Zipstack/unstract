"""Seed helpers for the deployment and pipeline list filter and aggregate tests."""

import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import jsonschema
from account_v2.models import Organization, User
from api_v2.models import APIDeployment
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin
from pipeline_v2.models import Pipeline
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from utils.user_context import UserContext

from unstract.core.data_models import ExecutionStatus
from workflow_manager.workflow_v2.failing_streaks import FAILING_STREAK_RUNS
from workflow_manager.workflow_v2.list_aggregates import FAILING_LIST_CAP
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

ERROR = ExecutionStatus.ERROR.value
COMPLETED = ExecutionStatus.COMPLETED.value
STOPPED = ExecutionStatus.STOPPED.value
PENDING = ExecutionStatus.PENDING.value
EXECUTING = ExecutionStatus.EXECUTING.value

FIVE_ERRORS = [ERROR] * 5


class ListRowsSeed(CoOwnerOrgTestMixin):
    """An org with members, a second org, and builders for rows and their runs."""

    # The viewset and list URL that _list and _aggregate call.
    view: Any = None
    url = ""

    def setUp(self) -> None:
        self._seed_org()
        self.now = timezone.now().replace(microsecond=0)
        self.org_b = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )

    def tearDown(self) -> None:
        # Left set, this thread-local scopes the managers in whatever runs next.
        UserContext.set_organization_identifier(None)  # type: ignore[arg-type]

    def _workflow(self, org: Organization | None = None) -> Workflow:
        workflow: Workflow = Workflow.objects.create(
            workflow_name=f"wf-{uuid.uuid4().hex[:8]}",
            organization=org or self.org,
            created_by=self.owner,
        )
        return workflow

    def _deployment(
        self,
        name: str,
        org: Organization | None = None,
        owner: User | None = None,
        **fields: Any,
    ) -> APIDeployment:
        row: APIDeployment = APIDeployment.objects.create(
            api_name=f"api-{uuid.uuid4().hex[:8]}",
            display_name=name,
            workflow=self._workflow(org),
            organization=org or self.org,
            created_by=self.owner,
            **fields,
        )
        row.grant_owner(owner or self.owner)
        return row

    def _pipeline(
        self,
        name: str,
        pipeline_type: str = "ETL",
        org: Organization | None = None,
        owner: User | None = None,
        **fields: Any,
    ) -> Pipeline:
        row: Pipeline = Pipeline.objects.create(
            pipeline_name=name,
            pipeline_type=pipeline_type,
            workflow=self._workflow(org),
            organization=org or self.org,
            created_by=self.owner,
            active=fields.pop("active", True),
            **fields,
        )
        row.grant_owner(owner or self.owner)
        return row

    def _share(self, row: Any, user: User) -> None:
        row.memberships.create(user=user, role=ResourceRole.VIEWER)

    def _runs(
        self,
        row: Any,
        statuses_oldest_first: list[str],
        hours_ago: int = 10,
        **fields: Any,
    ) -> None:
        """One run per status, an hour apart, the oldest ``hours_ago`` hours ago."""
        # bulk_create skips the post-save hooks, which reach Redis.
        runs = WorkflowExecution.objects.bulk_create(
            [
                WorkflowExecution(
                    workflow=row.workflow, pipeline_id=row.pk, status=status, **fields
                )
                for status in statuses_oldest_first
            ]
        )
        for offset, run in enumerate(runs):
            WorkflowExecution.objects.filter(pk=run.pk).update(
                created_at=self.now - timedelta(hours=hours_ago - offset)
            )

    def _call(
        self, view: Any, action: str, user: User, url: str, **params: Any
    ) -> Response:
        request = APIRequestFactory().get(url, params)
        force_authenticate(request, user=user)
        response: Response = view.as_view({"get": action})(request)
        return response

    def _list(self, user: User | None = None, **params: Any) -> Any:
        response = self._call(self.view, "list", user or self.admin, self.url, **params)
        return _ok(response)

    def _aggregate(self, user: User | None = None, **params: Any) -> Any:
        url = f"{self.url}aggregate/"
        return _ok(self._call(self.view, "aggregate", user or self.admin, url, **params))

    def _retrieve(self, row: Any, **params: Any) -> Response:
        request = APIRequestFactory().get(f"{self.url}{row.pk}/", params)
        force_authenticate(request, user=self.owner)
        response: Response = self.view.as_view({"get": "retrieve"})(request, pk=row.pk)
        return response

    def _hours_ago(self, timestamp: str) -> float:
        elapsed: timedelta = self.now - datetime.fromisoformat(timestamp)
        return elapsed / timedelta(hours=1)

    def _list_with_and_without_the_filter_step(self, **params: Any) -> tuple[Any, Any]:
        """The list's body and SQL, then both with the viewset's filter step removed."""

        def body_and_sql() -> tuple[Any, list[str]]:
            with CaptureQueriesContext(connection) as queries:
                body = self._list(**params)
            return body, [query["sql"] for query in queries]

        body_and_sql()  # Warm the per-process caches both runs read.
        with mock.patch.object(
            self.view, "filter_queryset", GenericAPIView.filter_queryset
        ):
            without_the_step = body_and_sql()
        return body_and_sql(), without_the_step

    def _mismatches_with_the_list(self, cases: list[dict[str, Any]]) -> list[str]:
        """Each caller and filter for which ``aggregate/`` disagrees with the list."""
        found: list[str] = []
        for user in (self.owner, self.coowner, self.viewer, self.outsider, self.admin):
            for params in cases:
                listed = self._list(user, **params)
                summary = self._aggregate(user, **params)
                failing = self._list(user, **{**params, "failing": "true"})
                got = (
                    summary["total"],
                    sum(summary["by_status"].values()),
                    summary["failing_count"],
                )
                want = (listed["count"], listed["count"], failing["count"])
                if got != want:
                    found.append(f"{user.email} {params}: {got} != {want}")
        return found


def _ok(response: Response) -> Any:
    assert response.status_code == 200, response.data
    return response.data


class AggregateRouteChecks:
    """Tests both aggregate routes share; ``contract`` is the response's JSON Schema."""

    contract: dict[str, Any] = {}

    def test_the_response_matches_the_contract(self: Any) -> None:
        self.assertIn("date-time", jsonschema.FormatChecker().checkers)
        cases: list[dict[str, Any]] = [{}, {"search": "no such row"}]
        for params in cases:
            with self.subTest(**params):
                jsonschema.validate(
                    self._aggregate(**params),
                    self.contract,
                    format_checker=jsonschema.FormatChecker(),
                )

    def test_the_contract_limits_match_the_code(self: Any) -> None:
        failing = self.contract["properties"]["failing"]
        self.assertEqual(failing["maxItems"], FAILING_LIST_CAP)
        row = self.contract["$defs"]["failingRow"]["properties"]
        self.assertEqual(row["failures_in_a_row"]["minimum"], FAILING_STREAK_RUNS)

    def test_a_partly_failed_latest_run_has_its_own_status(self: Any) -> None:
        self._runs(self.ok, [COMPLETED], hours_ago=1, successful_files=1, failed_files=1)
        listed = self._list(status="partial_success")["results"]

        self.assertEqual([str(row["id"]) for row in listed], [str(self.ok.pk)])
        self.assertEqual(self._aggregate()["by_status"]["partial_success"], 1)
        cases: list[dict[str, Any]] = [{}, {"status": "partial_success"}]
        self.assertEqual(self._mismatches_with_the_list(cases), [])

    def test_detail_routes_ignore_the_list_filters(self: Any) -> None:
        for params in ({"status": "error"}, {"status": "bogus"}, {"failing": "true"}):
            with self.subTest(**params):
                self.assertEqual(self._retrieve(self.ok, **params).status_code, 200)
