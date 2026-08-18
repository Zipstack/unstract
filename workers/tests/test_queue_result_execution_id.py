"""UN-3655: ``QueueResult`` carries ``execution_id`` into the HITL queue message.

These tests pin the **producer half** of the contract — that the ETL
manual-review push emits a queue message with a key named exactly
``execution_id`` (carrying the connector's value), so the downstream column
stops being NULL. The consumer half (``pluggable_apps.manual_review_v2`` writing
``hitl_queue.execution_id``) lives out-of-tree and is context, not something
these tests guarantee.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from shared.enums import QueueResultStatus
from shared.models.result_models import QueueResult


def _result(**overrides):
    kwargs = {
        "file": "doc.pdf",
        "status": QueueResultStatus.SUCCESS,
        "result": {"k": "v"},
        "workflow_id": "wf-1",
        "file_execution_id": "fexec-1",
        "execution_id": "exec-1",
    }
    kwargs.update(overrides)
    return QueueResult(**kwargs)


def test_to_dict_includes_execution_id():
    # The backend reads message["execution_id"] — the key + value must survive.
    d = _result().to_dict()
    assert d["execution_id"] == "exec-1"
    # And it sits alongside file_execution_id (both correlate the review item).
    assert d["file_execution_id"] == "fexec-1"


def test_execution_id_defaults_to_none_but_key_present_and_warns(caplog):
    # Callers that don't pass it must not break — the key is still emitted
    # (None), so the consumer's .get("execution_id") is a clean NULL, not a
    # KeyError, and the field is purely additive. But a missing value is a
    # latent NULL write, so __post_init__ logs a WARNING rather than failing
    # silently (we keep it optional — not a hard raise — because the connector's
    # execution_id is nullable on some paths).
    with caplog.at_level(logging.WARNING, logger="shared.models.result_models"):
        d = QueueResult(
            file="doc.pdf",
            status=QueueResultStatus.SUCCESS,
            result={},
            workflow_id="wf-1",
        ).to_dict()
    assert "execution_id" in d
    assert d["execution_id"] is None
    assert any(
        r.levelno == logging.WARNING and "execution_id" in r.message
        for r in caplog.records
    )


def test_no_warning_when_execution_id_present(caplog):
    with caplog.at_level(logging.WARNING, logger="shared.models.result_models"):
        _result()
    assert not any("execution_id" in r.message for r in caplog.records)


def test_push_data_to_queue_wires_connector_execution_id():
    """The integration line ``execution_id=self.execution_id`` (the point of the
    PR) — assert the dict handed to the enqueue boundary carries the connector's
    execution_id, distinct from file_execution_id, so a dropped kwarg or an
    adjacent-field swap is caught (the to_dict() tests above can't see that line).
    """
    from shared.workflow.destination_connector import WorkerDestinationConnector

    # Bypass the heavy config-driven __init__; set only what _push_data_to_queue
    # reads, with execution_id deliberately != file_execution_id.
    conn = WorkerDestinationConnector.__new__(WorkerDestinationConnector)
    conn.execution_id = "EXEC-distinct"
    conn.file_execution_id = "CONNECTOR-FEXEC"
    conn.workflow_id = "wf-1"
    conn.organization_id = "org-1"
    conn.is_api = False
    conn.hitl_queue_name = None
    conn.hitl_packet_id = None
    conn.workflow_log = MagicMock()
    conn._ensure_manual_review_service = MagicMock()
    conn._ensure_manual_review_service.return_value.get_workflow_util.return_value.get_hitl_ttl_seconds.return_value = 3600
    conn._get_review_queue_name = MagicMock(return_value="review_q")
    conn._read_file_from_source_connector = MagicMock(return_value="b64")
    conn.get_metadata = MagicMock(return_value={"whisper-hash": "wh"})
    conn._enqueue_to_packet_or_regular_queue = MagicMock()

    with (
        patch(
            "shared.workflow.destination_connector.has_manual_review_plugin",
            return_value=True,
        ),
        patch("shared.workflow.destination_connector.log_file_info"),
    ):
        conn._push_data_to_queue(
            file_name="doc.pdf",
            workflow={},
            input_file_path="/in/doc.pdf",
            file_execution_id="ARG-FEXEC",
            tool_execution_result="result-text",
            api_client=MagicMock(),
            hitl_reason="rule",
        )

    assert conn._enqueue_to_packet_or_regular_queue.called
    queue_result = conn._enqueue_to_packet_or_regular_queue.call_args.kwargs[
        "queue_result"
    ]
    assert queue_result["execution_id"] == "EXEC-distinct"  # from self.execution_id
    assert queue_result["file_execution_id"] == "ARG-FEXEC"
    # Adjacent-field swap (execution_id=self.file_execution_id / the arg) detectable:
    assert queue_result["execution_id"] != queue_result["file_execution_id"]
