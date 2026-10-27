"""GET workflow-execution: fetched once per step, file-execution rows only on demand.

The internal endpoint defaults ``file_execution`` to true and then loads every
file-execution row of the execution. Workers called it about 8 times per document,
and the client never sent ``file_execution=false``, so every call paid for those
rows (quadratic in the file count for an ETL run). These tests pin:

* the client always sends ``file_execution`` explicitly and defaults it to false;
* only the callback's context fetch asks for the rows (billing reads them);
* the callback's status step reuses that fetch instead of two more GETs;
* a file fetches once, and its source config lookup reuses that fetch.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import callback.tasks as cb
import pytest
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


class TestCallbackFetchesOnce:
    def _api(self, data):
        api = MagicMock()
        api.get_workflow_execution.return_value = MagicMock(success=True, data=data)
        return api

    def test_extract_requests_file_executions_and_keeps_context(self):
        data = _execution_context(pipeline_id="p")
        data["file_executions"] = [{"id": "f1", "status": "COMPLETED"}]
        api = self._api(data)
        task = MagicMock()
        task.request.id = "t1"
        with (
            patch.object(cb, "create_api_client", return_value=api),
            patch.object(cb, "_fetch_pipeline_name_from_api", return_value="pipe"),
        ):
            context = cb._extract_callback_parameters(
                task, [], {"execution_id": "e1", "organization_id": "org-1"}
            )

        api.get_workflow_execution.assert_called_once_with("e1", file_execution=True)
        assert context.execution_context is data
        # Billing still sees the rows it commits usage for.
        assert context.file_executions == data["file_executions"]

    def test_status_determination_reuses_execution_context(self):
        created = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        data = _execution_context(created_at=created)
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
        # Unchanged semantics: total_files is read from the top level, as before.
        assert expected_files == 0
        assert status == ExecutionStatus.COMPLETED.value

    def test_api_callback_passes_its_context_to_status_step(self):
        data = _execution_context()
        data["file_executions"] = [{"id": "f1", "status": "COMPLETED"}]
        api = self._api(data)
        task = MagicMock()
        task.request.id = "t1"
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
        assert seen["execution_context"] is data


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
