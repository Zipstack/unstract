"""UN-3749: the internal execution-data endpoint must not read ``completed_files``.

``WorkflowExecution`` has no such column (it has ``successful_files`` and
``failed_files``), so the endpoint raised ``AttributeError`` inside its broad
``except`` and answered 500 for every execution.

DB-free: the queryset is mocked and the row is an unsaved model instance, so a
missing field raises as it would in production.
"""

from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from workflow_manager import internal_api_views
from workflow_manager.workflow_v2.models.execution import WorkflowExecution


def _call(row):
    request = APIRequestFactory().get(
        "/internal/v1/workflow-manager/execution/x/",
        HTTP_X_ORGANIZATION_ID="org1",
    )
    with patch.object(internal_api_views, "WorkflowExecution") as wf_exec:
        wf_exec.objects.select_related.return_value.get.return_value = row
        return internal_api_views.get_workflow_execution_data(request, "x")


def _row(**counters):
    row = WorkflowExecution(status="COMPLETED", total_files=5, **counters)
    # Serve the FK from Django's own relation cache, with no DB.
    row._state.fields_cache["workflow"] = MagicMock(
        id="wf-1", workflow_name="wf", execution_details={}, organization_id="org1"
    )
    return row


def test_completed_files_is_successful_files():
    # Same meaning as the execution cache: completed and failed are disjoint,
    # so completed + failed is the processed count, not 5 of 4.
    response = _call(_row(successful_files=3, failed_files=1))

    assert response.status_code == 200, response.data
    execution = response.data["execution"]
    assert execution["completed_files"] == 3
    assert execution["failed_files"] == 1


def test_null_counters_pass_through():
    response = _call(_row(successful_files=None, failed_files=None))

    assert response.status_code == 200, response.data
    assert response.data["execution"]["completed_files"] is None
