"""GET workflow-execution: fetched once per step, file-execution rows only on demand.

These tests pin:

* the client always sends ``file_execution`` explicitly and defaults it to false;
* only the callback's context fetches ask for the rows, and billing sees rows
  only because they do;
* the callback's status step reuses that fetch instead of fetching again;
* each file fetches its context fresh, and its source and destination lookups
  reuse that fetch.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import callback.tasks as cb
import pytest
from shared.api.internal_client import InternalAPIClient
from shared.clients.execution_client import ExecutionAPIClient
from shared.processing.files.time_utils import WallClockTimeCalculator
from shared.workflow.execution.service import WorkerWorkflowExecutionService
from unstract.core.data_models import ExecutionStatus


def _execution_context(**execution):
    execution.setdefault("status", ExecutionStatus.EXECUTING.value)
    execution.setdefault("workflow_id", "wf")
    return {
        "execution": execution,
        "workflow_definition": {"workflow_id": "wf"},
        "source_config": {"type": "FILESYSTEM", "connector_id": "c1"},
        "destination_config": {"connection_type": "DATABASE"},
        "organization_context": {"organization_id": "org-1"},
        "file_executions": [],
    }


class TestClientQueryParams:
    """``ExecutionAPIClient.get_workflow_execution`` builds its query via params."""

    def _client(self):
        client = ExecutionAPIClient.__new__(ExecutionAPIClient)
        client.get = MagicMock(return_value={"execution": {}})
        return client

    def _params(self, client):
        assert client.get.call_count == 1
        url = client.get.call_args.args[0]
        assert "?" not in url, "query must go through params, not the URL"
        return client.get.call_args.kwargs["params"]

    def test_default_sends_file_execution_false(self):
        client = self._client()
        client.get_workflow_execution("e1")
        assert self._params(client) == {"file_execution": "false"}

    def test_file_execution_true_is_sent(self):
        client = self._client()
        client.get_workflow_execution("e1", file_execution=True)
        assert self._params(client) == {"file_execution": "true"}

    def test_include_cost_combines_with_file_execution(self):
        # Before: "?include_cost=true?file_execution=true" — the backend read
        # include_cost as "true?file_execution=true" and skipped the cost.
        client = self._client()
        client.get_workflow_execution("e1", include_cost=True, file_execution=True)
        assert self._params(client) == {
            "file_execution": "true",
            "include_cost": "true",
        }

    def test_organization_id_passed_through(self):
        client = self._client()
        client.get_workflow_execution("e1", organization_id="org-9")
        assert client.get.call_args.kwargs["organization_id"] == "org-9"

    def test_facade_passes_flags_through(self):
        facade = InternalAPIClient.__new__(InternalAPIClient)
        facade.execution_client = MagicMock()
        facade.execution_client.get_workflow_execution.return_value = {}
        with patch(
            "shared.api.internal_client.WorkflowExecutionResponse.from_api_response"
        ):
            facade.get_workflow_execution("e1", file_execution=True)
            facade.get_workflow_execution("e2")
        calls = facade.execution_client.get_workflow_execution.call_args_list
        assert calls[0].kwargs["file_execution"] is True
        assert calls[1].kwargs["file_execution"] is False


_ROWS = [{"id": "f1", "status": "COMPLETED"}]


def _flag_aware_api(**execution):
    """Fake that returns file-execution rows only when asked, like the backend."""

    def get_workflow_execution(execution_id, *args, file_execution=False, **kwargs):
        data = _execution_context(**execution)
        data["file_executions"] = list(_ROWS) if file_execution else []
        return MagicMock(success=True, data=data)

    api = MagicMock()
    api.get_workflow_execution.side_effect = get_workflow_execution
    return api


class TestCallbackFetchesOnce:

    def _task(self):
        task = MagicMock()
        task.request.id = "t1"
        return task

    def test_extract_requests_file_executions_and_keeps_context(self):
        api = _flag_aware_api(pipeline_id="p")
        with (
            patch.object(cb, "create_api_client", return_value=api),
            patch.object(cb, "_fetch_pipeline_name_from_api", return_value="pipe"),
        ):
            context = cb._extract_callback_parameters(
                self._task(), [], {"execution_id": "e1", "organization_id": "org-1"}
            )

        api.get_workflow_execution.assert_called_once_with("e1", file_execution=True)
        assert context.execution_context["execution"]["pipeline_id"] == "p"
        # Billing sees rows only because the fetch asked for them.
        assert context.file_executions == _ROWS

    def test_fallback_fetch_without_org_requests_file_executions(self):
        temp_api = _flag_aware_api(pipeline_id="p")
        org_api = MagicMock()
        with (
            patch.object(cb, "InternalAPIClient", return_value=temp_api),
            patch("shared.infrastructure.config.WorkerConfig"),
            patch.object(cb, "create_api_client", return_value=org_api),
            patch.object(cb, "_fetch_pipeline_name_from_api", return_value="pipe"),
        ):
            context = cb._extract_callback_parameters(
                self._task(), [], {"execution_id": "e1"}
            )

        temp_api.get_workflow_execution.assert_called_once_with(
            "e1", file_execution=True
        )
        org_api.get_workflow_execution.assert_not_called()
        assert context.organization_id == "org-1"
        assert context.file_executions == _ROWS

    def test_status_determination_reuses_execution_context(self):
        created = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        # total_files sits under "execution", as the serializer returns it.
        data = _execution_context(created_at=created, total_files=3)
        api = MagicMock()
        api.get_workflow_execution.side_effect = AssertionError("no extra GET")

        _, status, expected_files = cb._determine_execution_status_unified(
            file_batch_results=[],
            api_client=api,
            execution_id="e1",
            organization_id="org-1",
            execution_context=data,
        )

        api.get_workflow_execution.assert_not_called()
        # Known pre-existing bug, left as main has it: the top-level key is read,
        # so the nested count is missed and timeout detection never fires.
        # Fixing it changes final statuses and is tracked separately.
        assert expected_files == 0
        assert status == ExecutionStatus.COMPLETED.value

    def test_api_callback_passes_its_context_to_status_step(self):
        api = _flag_aware_api()
        task = self._task()
        seen = {}

        def determine(**kwargs):
            seen.update(kwargs)
            raise RuntimeError("stop after status step")

        with (
            patch.object(cb, "create_api_client", return_value=api),
            patch.object(
                cb, "_fetch_pipeline_data_simplified", return_value=("api", "API")
            ),
            patch.object(
                cb, "_determine_execution_status_unified", side_effect=determine
            ),
            pytest.raises(RuntimeError, match="stop after status step"),
        ):
            cb.process_batch_callback_api(
                task, [], execution_id="e1", organization_id="org-1", pipeline_id="p"
            )

        api.get_workflow_execution.assert_called_once_with("e1", file_execution=True)
        assert seen["execution_context"]["file_executions"] == _ROWS


class TestBillingWithoutRows:
    def _context(self, file_executions):
        context = cb.CallbackContext()
        context.execution_id = "e1"
        context.organization_id = "org-1"
        context.file_executions = file_executions
        return context

    def _track(self, context, successful_files):
        plugin = MagicMock()
        with (
            patch("client_plugin_registry.get_client_plugin", return_value=plugin),
            patch.object(cb.logger, "warning") as warning,
        ):
            result = cb._track_subscription_usage_if_available(
                context=context,
                execution_status=ExecutionStatus.COMPLETED.value,
                successful_files=successful_files,
            )
        return result, warning

    def test_warns_when_successful_files_have_no_rows(self):
        result, warning = self._track(self._context([]), successful_files=2)
        assert result["status"] == "skipped"
        warning.assert_called_once()
        assert "no file executions" in warning.call_args.args[0]

    def test_no_warning_when_nothing_succeeded(self):
        _, warning = self._track(self._context([]), successful_files=0)
        warning.assert_not_called()


class TestWallClockReuse:
    def test_uses_given_context_without_fetching(self):
        created = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        api = MagicMock()
        api.get_workflow_execution.side_effect = AssertionError("no extra GET")

        elapsed = WallClockTimeCalculator.calculate_execution_time(
            api, "e1", "org-1", [], execution_context=_execution_context(created_at=created)
        )

        assert 29 <= elapsed <= 60
        api.get_workflow_execution.assert_not_called()

    def test_falls_back_to_file_times_when_context_lacks_created_at(self):
        api = MagicMock()
        elapsed = WallClockTimeCalculator.calculate_execution_time(
            api,
            "e1",
            "org-1",
            [{"processing_time": 2.0}, {"processing_time": 3.0}],
            execution_context=_execution_context(),
        )
        assert elapsed == pytest.approx(5.0)
        api.get_workflow_execution.assert_not_called()


class TestPerFileReuse:
    """Each file fetches its execution context once, without file-execution rows.

    It is fetched per file, not taken from the batch, so a long batch still sees
    connector settings (auth tokens) as they are when each file starts.
    """

    def _service(self):
        api = MagicMock()
        api.get_workflow_execution.return_value = MagicMock(
            success=True, data=_execution_context(pipeline_id="p")
        )
        api.get_tool_instances_by_workflow.return_value = MagicMock(
            tool_instances=[{"id": "t"}]
        )
        return WorkerWorkflowExecutionService(api_client=api), api

    def test_config_lookups_reuse_the_files_fetch(self):
        service, api = self._service()

        context, tools = service._get_workflow_execution_context("e1", "wf", "org-1")
        source = service._get_source_config("wf", "e1")
        destination = service._get_destination_config("wf", "e1")

        api.get_workflow_execution.assert_called_once_with("e1")
        assert tools == [{"id": "t"}]
        assert source == context["source_config"]
        assert destination == context["destination_config"]

    def test_same_instance_refetches_per_file(self):
        service, api = self._service()
        service._get_workflow_execution_context("e1", "wf", "org-1")
        service._get_workflow_execution_context("e1", "wf", "org-1")
        assert api.get_workflow_execution.call_count == 2

    def test_each_file_fetches_fresh(self):
        # One service per file (processor.py); a second file must not see the
        # first file's context.
        first, api = self._service()
        first._get_workflow_execution_context("e1", "wf", "org-1")
        second = WorkerWorkflowExecutionService(api_client=api)
        second._get_workflow_execution_context("e1", "wf", "org-1")
        assert api.get_workflow_execution.call_count == 2

    def test_source_config_alone_fetches(self):
        service, api = self._service()
        assert service._get_source_config("wf", "e1") == {
            "type": "FILESYSTEM",
            "connector_id": "c1",
        }
        api.get_workflow_execution.assert_called_once_with("e1")

    def test_failed_fetch_keeps_none_result(self):
        service, api = self._service()
        api.get_workflow_execution.return_value = MagicMock(success=False, error="x")
        assert service._get_source_config("wf", "e1") is None

    def test_failed_fetch_is_retried_by_a_later_lookup(self):
        service, api = self._service()
        api.get_workflow_execution.return_value = MagicMock(success=False, error="x")
        assert service._get_source_config("wf", "e1") is None
        api.get_workflow_execution.return_value = MagicMock(
            success=True, data=_execution_context()
        )
        assert service._get_source_config("wf", "e1") is not None

    def test_cached_context_is_not_served_for_another_execution(self):
        service, api = self._service()
        service._get_workflow_execution_context("e1", "wf", "org-1")
        service._get_source_config("wf", "e2")
        assert [c.args[0] for c in api.get_workflow_execution.call_args_list] == [
            "e1",
            "e2",
        ]


class TestMissingContextFallbacks:
    def test_status_step_tolerates_missing_context(self):
        api = MagicMock()
        api.get_workflow_execution.return_value = MagicMock(success=False, error="x")
        _, status, expected_files = cb._determine_execution_status_unified(
            file_batch_results=[],
            api_client=api,
            execution_id="e1",
            organization_id="org-1",
            execution_context=None,
        )
        assert expected_files == 0
        assert status == ExecutionStatus.COMPLETED.value

    def test_wall_clock_refetches_on_empty_context(self):
        created = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        api = MagicMock()
        api.get_workflow_execution.return_value = MagicMock(
            success=True, data=_execution_context(created_at=created)
        )
        elapsed = WallClockTimeCalculator.calculate_execution_time(
            api, "e1", "org-1", [], execution_context={}
        )
        assert 29 <= elapsed <= 60
        api.get_workflow_execution.assert_called_once()
