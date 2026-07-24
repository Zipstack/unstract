"""UN-3655: backend ``QueueResult`` carries ``execution_id`` (parity with the
workers ``QueueResult``).

The backend ``DestinationConnector`` is a second producer of the HITL queue
message. It must emit the same ``execution_id`` key so ``hitl_queue.execution_id``
is populated whichever destination path enqueues the review. Pins the producer
half only (the consumer column write lives in ``manual_review_v2``).
"""

from __future__ import annotations

import os

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from workflow_manager.endpoint_v2.queue_utils import (  # noqa: E402
    QueueResult,
    QueueResultStatus,
)


def test_backend_queue_result_to_dict_includes_execution_id():
    d = QueueResult(
        file="doc.pdf",
        status=QueueResultStatus.SUCCESS,
        result={"k": "v"},
        workflow_id="wf-1",
        file_content="b64",
        file_execution_id="fexec-1",
        execution_id="exec-1",
    ).to_dict()
    assert d["execution_id"] == "exec-1"
    assert d["file_execution_id"] == "fexec-1"


def test_backend_execution_id_defaults_to_none_but_key_present():
    d = QueueResult(
        file="doc.pdf",
        status=QueueResultStatus.SUCCESS,
        result={},
        workflow_id="wf-1",
        file_content="b64",
    ).to_dict()
    assert "execution_id" in d
    assert d["execution_id"] is None
