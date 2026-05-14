from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rest_framework import status, viewsets
from rest_framework.response import Response

from adapter_processor_v2.views import AdapterInstanceViewSet
from workflow_manager.workflow_v2.views import WorkflowViewSet


def test_workflow_partial_update_skips_shared_user_lookup_without_share_changes() -> None:
    view = WorkflowViewSet()
    workflow = MagicMock()
    workflow.shared_users.all.side_effect = AssertionError(
        "shared_users should not be queried for non-sharing updates"
    )
    request = SimpleNamespace(data={"workflow_name": "renamed"}, user=MagicMock())

    with (
        patch.object(WorkflowViewSet, "get_object", return_value=workflow),
        patch.object(
            viewsets.ModelViewSet,
            "partial_update",
            autospec=True,
            return_value=Response(status=status.HTTP_200_OK),
        ),
    ):
        response = view.partial_update(request)

    assert response.status_code == status.HTTP_200_OK
    workflow.shared_users.all.assert_not_called()


def test_adapter_partial_update_reuses_pre_update_shared_users() -> None:
    view = AdapterInstanceViewSet()
    shared_user_1 = SimpleNamespace(id=1)
    shared_user_2 = SimpleNamespace(id=2)
    adapter = MagicMock(adapter_type="LLM", adapter_name="Adapter", id=1)
    adapter.shared_users.all.side_effect = [
        [shared_user_1, shared_user_2],
        [shared_user_1, shared_user_2],
    ]
    request = SimpleNamespace(
        data={"shared_users": ["1", "2"]},
        user=MagicMock(),
    )

    with (
        patch.object(AdapterInstanceViewSet, "get_object", return_value=adapter),
        patch.object(
            viewsets.ModelViewSet,
            "partial_update",
            autospec=True,
            return_value=Response(status=status.HTTP_200_OK),
        ),
    ):
        response = view.partial_update(request)

    assert response.status_code == status.HTTP_200_OK
    assert adapter.shared_users.all.call_count == 2
