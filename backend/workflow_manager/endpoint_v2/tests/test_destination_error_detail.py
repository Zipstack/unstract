"""Destination read failures must not put the execution-storage path in the
``APIException`` detail returned to the caller (CodeQL py/stack-trace-exposure).

The path (bucket/org/workflow/execution layout) still goes to the server log.
"""

from __future__ import annotations

import os
from unittest import mock

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from rest_framework.exceptions import APIException  # noqa: E402

from unstract.workflow_execution.constants import ToolOutputType  # noqa: E402
from workflow_manager.endpoint_v2 import destination  # noqa: E402
from workflow_manager.endpoint_v2.destination import DestinationConnector  # noqa: E402

STORAGE_PATH = "unstract-execution/org_abc/wf_123/exec_456/file_789/INFILE"


def _connector() -> DestinationConnector:
    connector = DestinationConnector.__new__(DestinationConnector)
    connector.infile = STORAGE_PATH
    connector.get_workflow_metadata = mock.Mock(return_value={})
    connector.get_output_type = mock.Mock(return_value=ToolOutputType.JSON)
    return connector


def _patched_storage(storage: mock.Mock):
    file_system = mock.Mock()
    file_system.return_value.get_file_storage.return_value = storage
    return mock.patch.object(destination, "FileSystem", file_system)


@pytest.mark.parametrize(
    ("read_error", "expected_detail"),
    [
        (
            FileNotFoundError(f"No such file: {STORAGE_PATH}"),
            "Error while getting result from the tool: output not found",
        ),
        (
            # ``doc`` is the file content, as json.loads would raise it.
            destination.json.JSONDecodeError("Expecting value", "", 0),
            "Error while getting result from the tool: output is not valid JSON",
        ),
    ],
)
def test_tool_result_error_hides_storage_path(read_error, expected_detail):
    storage = mock.Mock()
    storage.mime_type.return_value = "application/json"
    storage.read.side_effect = read_error

    with (
        _patched_storage(storage),
        mock.patch.object(destination.logger, "error") as log_error,
        pytest.raises(APIException) as exc_info,
    ):
        _connector().get_tool_execution_result_from_metadata()

    assert str(exc_info.value.detail) == expected_detail
    assert STORAGE_PATH not in str(exc_info.value.detail)
    assert STORAGE_PATH in log_error.call_args.args[0]


@pytest.mark.parametrize(
    "storage_setup",
    [
        pytest.param({"exists.return_value": False}, id="missing"),
        pytest.param(
            {
                "exists.return_value": True,
                "read.side_effect": OSError(f"read failed: {STORAGE_PATH}"),
            },
            id="read-error",
        ),
    ],
)
def test_queue_file_read_error_hides_storage_path(storage_setup):
    storage = mock.Mock(**storage_setup)

    with (
        _patched_storage(storage),
        mock.patch.object(destination.logger, "error") as log_error,
        pytest.raises(APIException) as exc_info,
    ):
        _connector()._read_file_content_for_queue(STORAGE_PATH, "invoice.pdf")

    detail = str(exc_info.value.detail)
    assert detail == "Failed to read file content for queue: invoice.pdf"
    assert STORAGE_PATH not in detail
    assert STORAGE_PATH in log_error.call_args.args[0]
