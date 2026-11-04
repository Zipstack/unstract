"""The HITL queue read must not put the execution-storage path in the error
that reaches the caller (CodeQL py/stack-trace-exposure, worker counterpart of
the backend ``DestinationConnector._read_file_content_for_queue``).

The path still goes to the worker log.
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from shared.workflow import destination_connector
from shared.workflow.destination_connector import WorkerDestinationConnector

STORAGE_PATH = "unstract-execution/org_abc/wf_123/exec_456/file_789/INFILE"


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
    file_system = mock.Mock()
    file_system.return_value.get_file_storage.return_value = storage
    connector = WorkerDestinationConnector.__new__(WorkerDestinationConnector)

    logged = []

    with (
        mock.patch.object(destination_connector, "FileSystem", file_system),
        mock.patch.object(
            destination_connector.logger,
            "exception",
            # exc_info=False would log no traceback, so record nothing handled.
            side_effect=lambda msg, *a, **k: logged.append(
                (msg, sys.exc_info()[1] if k.get("exc_info", True) else None)
            ),
        ),
    ):
        with pytest.raises(OSError) as exc_info:
            connector._read_file_content_for_queue(STORAGE_PATH, "invoice.pdf")

    assert str(exc_info.value) == "Failed to read file content for queue: invoice.pdf"
    # The path reaches the log through the handled exception's traceback.
    [(message, handled)] = logged
    assert message == "Failed to read file content for invoice.pdf"
    assert STORAGE_PATH in str(handled)
