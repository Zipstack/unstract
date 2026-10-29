"""The stuck/abort additions leave the existing execution endpoints unchanged,
and their published contract generates (UN-4318)."""

import uuid
from typing import Any

from django.test import SimpleTestCase
from django.urls import resolve, reverse
from drf_spectacular.generators import SchemaGenerator
from pipeline_v2.models import Pipeline
from rest_framework.test import APIRequestFactory

from workflow_manager.execution import urls
from workflow_manager.execution.tests.stuck_abort_base import StuckAbortTestBase
from workflow_manager.execution.views import ExecutionViewSet
from workflow_manager.internal_views import WorkflowExecutionInternalViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus

_URLCONF = "workflow_manager.execution.urls"
_list = ExecutionViewSet.as_view({"get": "list"})
_detail = ExecutionViewSet.as_view({"get": "retrieve"})
_status = WorkflowExecutionInternalViewSet.as_view({"get": "execution_status"})

# The default row, pinned: a new key here is a contract change.
_EXECUTION_KEYS = {
    "aggregated_total_pages_processed",
    "attempts",
    "created_at",
    "dispatched_at",
    "error_message",
    "execution_method",
    "execution_mode",
    "execution_time",
    "failed_files",
    "id",
    "modified_at",
    "pipeline_id",
    "pipeline_name",
    "queue_message_id",
    "result_acknowledged",
    "status",
    "successful_files",
    "tags",
    "total_files",
    "workflow",
    "workflow_name",
}


class ExistingResponsesUnchangedTests(StuckAbortTestBase):
    def test_list_and_detail_keep_their_keys(self) -> None:
        execution = self.execution()
        listed = self.call(_list, self.owner)
        self.assertEqual(set(listed.data["results"][0]), _EXECUTION_KEYS)
        detail = self.call(_detail, self.owner, pk=str(execution.id))
        self.assertEqual(set(detail.data), _EXECUTION_KEYS)

    def test_stuck_false_is_the_same_response_as_no_parameter(self) -> None:
        self.execution()
        self.execution(status=ExecutionStatus.COMPLETED)
        plain = self.call(_list, self.owner)
        for value in ("false", "0", ""):
            with self.subTest(stuck=value):
                filtered = self.call(_list, self.owner, data={"stuck": value})
                self.assertEqual(filtered.content, plain.content)

    def test_entity_filter_still_selects_each_entity(self) -> None:
        runs = {
            "API": self.execution(self.deployment()),
            "ETL": self.execution(self.pipeline(Pipeline.PipelineType.ETL)),
            "TASK": self.execution(self.pipeline(Pipeline.PipelineType.TASK)),
            "WF": self.execution(),
        }
        for entity, run in runs.items():
            with self.subTest(entity=entity):
                response = self.call(
                    _list, self.owner, data={"execution_entity": entity}
                )
                ids = [row["id"] for row in response.data["results"]]
                self.assertEqual(ids, [str(run.id)])

    def test_stuck_rows_add_only_stuck_since(self) -> None:
        self.execution()
        listed = self.call(_list, self.owner, data={"stuck": "true"})
        self.assertEqual(
            set(listed.data["results"][0]), _EXECUTION_KEYS | {"stuck_since"}
        )


class InternalStatusActionTests(StuckAbortTestBase):
    def _get(self, execution_id: Any, organization_id: str | None) -> Any:
        request = APIRequestFactory().get("/")
        request.organization_id = organization_id
        return _status(request, id=str(execution_id))

    def test_returns_the_status(self) -> None:
        execution = self.execution(status=ExecutionStatus.STOPPED)
        response = self._get(execution.id, self.org.organization_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, {"id": str(execution.id), "status": "STOPPED"}
        )

    def test_other_org_unknown_and_malformed_ids_are_404(self) -> None:
        execution = self.execution()
        cases = (
            (execution.id, "some-other-org"),
            (execution.id, None),
            (uuid.uuid4(), self.org.organization_id),
            ("not-a-uuid", self.org.organization_id),
        )
        for execution_id, organization_id in cases:
            with self.subTest(execution_id=execution_id, org=organization_id):
                response = self._get(execution_id, organization_id)
                self.assertEqual(response.status_code, 404)


class RoutesUnchangedTests(SimpleTestCase):
    def test_existing_names_reverse_to_the_same_paths(self) -> None:
        pk = uuid.uuid4()
        expected = {
            ("execution-list", None): "/",
            ("execution-detail", pk): f"/{pk}/",
            ("execution-log", pk): f"/{pk}/logs/",
            ("execution-log-export", pk): f"/{pk}/logs/export/",
            ("execution-stuck-count", None): "/stuck-count/",
            ("execution-abort", None): "/abort/",
        }
        for (name, key), path in expected.items():
            kwargs = {"pk": key} if key else None
            with self.subTest(name=name):
                self.assertEqual(reverse(name, urlconf=_URLCONF, kwargs=kwargs), path)

    def test_new_paths_do_not_shadow_detail(self) -> None:
        self.assertEqual(
            resolve("/stuck-count/", urlconf=_URLCONF).url_name,
            "execution-stuck-count",
        )
        self.assertEqual(
            resolve(f"/{uuid.uuid4()}/", urlconf=_URLCONF).url_name,
            "execution-detail",
        )


class SchemaContractTests(SimpleTestCase):
    """The ``@extend_schema`` annotations and README.md are the contract."""

    def test_schema_documents_the_new_operations(self) -> None:
        schema = SchemaGenerator(patterns=urls.urlpatterns).get_schema(
            request=None, public=True
        )
        paths = schema["paths"]
        count = paths["/stuck-count/"]["get"]
        self.assertEqual(count["operationId"], "execution_stuck_count")
        self.assertTrue({"200", "403"} <= set(count["responses"]))

        abort = paths["/abort/"]["post"]
        self.assertEqual(abort["operationId"], "execution_abort")
        self.assertTrue({"200", "400", "403"} <= set(abort["responses"]))
        components = schema["components"]["schemas"]
        self.assertIn("ids", components["ExecutionAbortRequest"]["properties"])
        self.assertEqual(
            set(components["ExecutionAbortResponse"]["properties"]),
            {"results", "aborted", "already_finished", "not_permitted"},
        )
        self.assertEqual(
            set(components["StuckExecutionCount"]["properties"]),
            {"threshold_seconds", "total", "counts"},
        )

        list_params = {p["name"] for p in paths["/"]["get"]["parameters"]}
        self.assertIn("stuck", list_params)
