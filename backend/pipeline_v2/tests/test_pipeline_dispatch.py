"""Unit tests for the API-triggered pipeline-trigger dispatch (UN-3616, UN-4046).

``enqueue_task`` is patched on the module, so no DB is needed. These pin the
payload contract the ``scheduler`` consumer depends on, and the no-silent-fallback
property.

The transport-routing tests are gone with the ``pg_queue_enabled`` flag (UN-4046):
there is no Celery branch left to choose, so "routes to celery", "resolve_transport
called with the pipeline as entity" and "args identical on both paths" no longer
describe anything. What survives is what the consumer actually sees.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

import pipeline_v2.pipeline_dispatch as pd

_EXPECTED_ARGS = ["", "org_x", "", "", "pid-1", True, "My Pipeline"]


def _dispatch():
    return pd.dispatch_pipeline_trigger(
        org_id="org_x",
        pipeline_id="pid-1",
        pipeline_name="My Pipeline",
    )


class TestDispatchPipelineTrigger:
    def test_enqueues_on_the_pg_scheduler_queue(self):
        with patch.object(pd, "enqueue_task", return_value=42) as enqueue:
            _dispatch()
        enqueue.assert_called_once()
        kwargs = enqueue.call_args.kwargs
        assert kwargs["task_name"] == "scheduler.tasks.execute_pipeline_task"
        assert kwargs["queue"] == "scheduler"
        assert kwargs["args"] == _EXPECTED_ARGS
        assert kwargs["org_id"] == "org_x"

    def test_pg_enqueue_failure_propagates(self):
        # The dispatcher has no try/except → a PG enqueue failure must surface to
        # the caller rather than being swallowed into a silent no-dispatch.
        with patch.object(pd, "enqueue_task", side_effect=RuntimeError("pg down")):
            with pytest.raises(RuntimeError, match="pg down"):
                _dispatch()

    def test_uuid_pipeline_id_is_coerced_to_str_in_args(self):
        # The signature accepts a UUID, but the task args must carry strings —
        # enqueue_task JSON-normalizes, and the consumer unpacks positionally.
        pid = uuid.UUID("b1f16024-45f2-4e39-8756-d40e24148e30")
        with patch.object(pd, "enqueue_task", return_value=1) as enqueue:
            pd.dispatch_pipeline_trigger(
                org_id="org_x", pipeline_id=pid, pipeline_name="P"
            )
        assert enqueue.call_args.kwargs["args"][4] == str(pid)
