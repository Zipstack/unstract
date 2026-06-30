"""UN-3655: ``QueueResult`` carries ``execution_id`` into the HITL queue message.

The ETL manual-review push serialises a ``QueueResult`` to the queue message; the
backend manual-review enqueue persists ``hitl_queue.execution_id`` from
``message["execution_id"]``. These tests pin that contract — the key must be
present (and named exactly ``execution_id``) so the column stops being NULL.
"""

from __future__ import annotations

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


def test_execution_id_defaults_to_none_but_key_present():
    # Older callers that don't pass it must not break — the key is still emitted
    # (None), so the backend's .get("execution_id") is a clean NULL, not a
    # KeyError, and the field is purely additive.
    d = QueueResult(
        file="doc.pdf",
        status=QueueResultStatus.SUCCESS,
        result={},
        workflow_id="wf-1",
    ).to_dict()
    assert "execution_id" in d
    assert d["execution_id"] is None
