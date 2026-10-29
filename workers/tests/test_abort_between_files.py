"""A running batch stops between files once its execution is STOPPED (UN-4318).

Pins: the status is checked before each file; only STOPPED (abort) stops the
batch, with the remaining files counted as failed and their rows marked
STOPPED; any other status, or a failed check, processes the file (fail open).
Also pins the client URL and the facade delegation.
"""

from __future__ import annotations

import types
from typing import Any
from unittest import mock

import pytest
from unstract.core.data_models import ExecutionStatus, FileBatchResult

from file_processing.tasks import _file_item_name, _process_individual_files

_TASKS = "file_processing.tasks"


def _context(api_client: Any, n_files: int = 3) -> Any:
    files = {
        f"file_{i}": {"file_name": f"f{i}.pdf", "file_path": f"/in/f{i}.pdf"}
        for i in range(n_files)
    }
    pre_created = {
        f"f{i}.pdf": mock.Mock(
            id=f"fe-{i}",
            file_hash=mock.Mock(is_manualreview_required=False),
        )
        for i in range(n_files)
    }
    return types.SimpleNamespace(
        files=files,
        execution_id="exec-1",
        workflow_id="wf-1",
        pre_created_file_executions=pre_created,
        organization_context=types.SimpleNamespace(api_client=api_client),
        get_setting=lambda key, default=None: default,
        metadata={
            "file_data": mock.Mock(),
            "workflow_execution": {},
            "result": FileBatchResult(),
            "successful_files_for_manual_review": [],
            "total_files": n_files,
            "workflow_logger": None,
        },
    )


def _run(api_client: Any, n_files: int = 3) -> tuple[FileBatchResult, Any]:
    """Run the loop with file processing stubbed to succeed."""
    context = _context(api_client, n_files)

    def _succeeded(
        _result: Any, _name: Any, _start: Any, result: Any, *args: Any, **kwargs: Any
    ) -> None:
        result.increment_success()

    with (
        mock.patch(f"{_TASKS}._process_file") as process_file,
        mock.patch(
            f"{_TASKS}._handle_file_processing_result", side_effect=_succeeded
        ),
        mock.patch(f"{_TASKS}.log_file_processing_start"),
        mock.patch(f"{_TASKS}.log_file_info"),
    ):
        _process_individual_files(context)
    return context.metadata["result"], process_file


def _stopped_ids(api_client: Any) -> list[str]:
    return [
        c.kwargs["file_execution_id"]
        for c in api_client.update_file_execution_status.call_args_list
        if c.kwargs["status"] == ExecutionStatus.STOPPED.value
    ]


def test_stops_after_the_status_flips_to_stopped() -> None:
    api_client = mock.Mock()
    api_client.get_workflow_execution_status.side_effect = [
        ExecutionStatus.EXECUTING.value,
        ExecutionStatus.STOPPED.value,
    ]

    result, process_file = _run(api_client)

    assert process_file.call_count == 1
    assert api_client.get_workflow_execution_status.call_count == 2
    assert _stopped_ids(api_client) == ["fe-1", "fe-2"]
    assert (result.successful_files, result.failed_files) == (1, 2)


def test_stopped_before_the_first_file_processes_nothing() -> None:
    api_client = mock.Mock()
    api_client.get_workflow_execution_status.return_value = (
        ExecutionStatus.STOPPED.value
    )

    result, process_file = _run(api_client)

    process_file.assert_not_called()
    assert _stopped_ids(api_client) == ["fe-0", "fe-1", "fe-2"]
    assert (result.successful_files, result.failed_files) == (0, 3)


def test_a_failed_stopped_write_does_not_stop_the_rest() -> None:
    api_client = mock.Mock()
    api_client.get_workflow_execution_status.return_value = (
        ExecutionStatus.STOPPED.value
    )
    api_client.update_file_execution_status.side_effect = RuntimeError("500")

    result, process_file = _run(api_client)

    process_file.assert_not_called()
    assert _stopped_ids(api_client) == ["fe-0", "fe-1", "fe-2"]
    assert (result.successful_files, result.failed_files) == (0, 3)


def test_error_mid_batch_keeps_processing_the_files() -> None:
    """Only an abort stops a running batch; ERROR keeps today's behaviour."""
    api_client = mock.Mock()
    api_client.get_workflow_execution_status.side_effect = [
        ExecutionStatus.EXECUTING.value,
        ExecutionStatus.ERROR.value,
        ExecutionStatus.ERROR.value,
    ]

    result, process_file = _run(api_client)

    assert process_file.call_count == 3
    assert _stopped_ids(api_client) == []
    assert (result.successful_files, result.failed_files) == (3, 0)


@pytest.mark.parametrize(
    "status",
    [
        ExecutionStatus.PENDING.value,
        ExecutionStatus.EXECUTING.value,
        ExecutionStatus.ERROR.value,
        ExecutionStatus.COMPLETED.value,
        None,
    ],
)
def test_any_other_status_processes_every_file(status: str | None) -> None:
    api_client = mock.Mock()
    api_client.get_workflow_execution_status.return_value = status

    result, process_file = _run(api_client)

    assert process_file.call_count == 3
    assert _stopped_ids(api_client) == []
    assert (result.successful_files, result.failed_files) == (3, 0)


def test_a_failed_check_processes_the_file_anyway() -> None:
    api_client = mock.Mock()
    api_client.get_workflow_execution_status.side_effect = RuntimeError("404")

    result, process_file = _run(api_client)

    assert process_file.call_count == 3
    assert _stopped_ids(api_client) == []
    assert result.successful_files == 3


@pytest.mark.parametrize(
    ("item", "name"),
    [
        (["a.pdf", {}], "a.pdf"),
        (("b.pdf", {}), "b.pdf"),
        ({"file_name": "c.pdf"}, "c.pdf"),
        (["too", "many", "parts"], None),
        (object(), None),
    ],
)
def test_file_item_name_reads_every_format(item: Any, name: str | None) -> None:
    assert _file_item_name(item) == name


def test_client_reads_the_status_endpoint() -> None:
    from shared.clients.execution_client import ExecutionAPIClient

    client = ExecutionAPIClient.__new__(ExecutionAPIClient)
    body = {"id": "exec-1", "status": "STOPPED"}
    with mock.patch.object(client, "get", return_value=body) as get:
        assert client.get_workflow_execution_status("exec-1", "org-1") == "STOPPED"
    get.assert_called_once_with(
        "v1/workflow-execution/exec-1/status/", organization_id="org-1"
    )


def test_client_returns_none_for_a_non_dict_body() -> None:
    from shared.clients.execution_client import ExecutionAPIClient

    client = ExecutionAPIClient.__new__(ExecutionAPIClient)
    with mock.patch.object(client, "get", return_value=None):
        assert client.get_workflow_execution_status("exec-1") is None


def test_facade_delegates_to_the_execution_client() -> None:
    from shared.api.internal_client import InternalAPIClient

    client = InternalAPIClient.__new__(InternalAPIClient)
    client.execution_client = mock.MagicMock()
    client.execution_client.get_workflow_execution_status.return_value = "ERROR"

    assert client.get_workflow_execution_status("exec-1", "org-1") == "ERROR"
    client.execution_client.get_workflow_execution_status.assert_called_once_with(
        "exec-1", "org-1"
    )
