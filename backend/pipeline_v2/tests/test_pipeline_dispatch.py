"""Unit tests for the API-triggered pipeline-trigger transport routing (UN-3616).

`resolve_transport` + `enqueue_task` are patched on the module, so no Flipt / DB
is needed — these pin the routing contract: PG when the flag resolves PG, Celery
otherwise (fail-closed), with byte-identical args on both paths.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

import pipeline_v2.pipeline_dispatch as pd

_EXPECTED_ARGS = ["", "org_x", "", "", "pid-1", True, "My Pipeline"]


def _dispatch(celery_app):
    return pd.dispatch_pipeline_trigger(
        celery_app=celery_app,
        org_id="org_x",
        pipeline_id="pid-1",
        pipeline_name="My Pipeline",
    )


class TestDispatchPipelineTrigger:
    def test_routes_to_pg_when_flag_resolves_pg(self):
        celery = MagicMock()
        with (
            patch.object(pd, "resolve_transport", return_value="pg_queue"),
            patch.object(pd, "enqueue_task", return_value=42) as enqueue,
        ):
            _dispatch(celery)
        enqueue.assert_called_once()
        kwargs = enqueue.call_args.kwargs
        assert kwargs["task_name"] == "scheduler.tasks.execute_pipeline_task"
        assert kwargs["queue"] == "scheduler"
        assert kwargs["args"] == _EXPECTED_ARGS
        assert kwargs["org_id"] == "org_x"
        celery.send_task.assert_not_called()

    def test_pg_enqueue_failure_propagates_with_no_celery_fallback(self):
        # The dispatcher has no try/except → a PG enqueue failure must surface
        # (no silent Celery fallback, which would risk a double-dispatch).
        celery = MagicMock()
        with (
            patch.object(pd, "resolve_transport", return_value="pg_queue"),
            patch.object(pd, "enqueue_task", side_effect=RuntimeError("pg down")),
        ):
            with pytest.raises(RuntimeError, match="pg down"):
                _dispatch(celery)
        celery.send_task.assert_not_called()

    def test_uuid_pipeline_id_is_coerced_to_str_in_args(self):
        # resolve_transport accepts a UUID, but the task args must carry strings.
        pid = uuid.UUID("b1f16024-45f2-4e39-8756-d40e24148e30")
        celery = MagicMock()
        with (
            patch.object(pd, "resolve_transport", return_value="pg_queue") as resolve,
            patch.object(pd, "enqueue_task", return_value=1) as enqueue,
        ):
            pd.dispatch_pipeline_trigger(
                celery_app=celery, org_id="org_x", pipeline_id=pid, pipeline_name="P"
            )
        assert enqueue.call_args.kwargs["args"][4] == str(pid)
        # The raw UUID is passed to resolve_transport as the sticky entity.
        assert resolve.call_args.kwargs["execution_id"] == pid

    def test_routes_to_celery_when_flag_resolves_celery(self):
        celery = MagicMock()
        with (
            patch.object(pd, "resolve_transport", return_value="celery"),
            patch.object(pd, "enqueue_task") as enqueue,
        ):
            _dispatch(celery)
        celery.send_task.assert_called_once_with(
            "scheduler.tasks.execute_pipeline_task", args=_EXPECTED_ARGS
        )
        enqueue.assert_not_called()

    def test_resolve_transport_called_with_pipeline_as_entity(self):
        celery = MagicMock()
        with (
            patch.object(pd, "resolve_transport", return_value="celery") as resolve,
            patch.object(pd, "enqueue_task"),
        ):
            _dispatch(celery)
        kwargs = resolve.call_args.kwargs
        assert kwargs["execution_id"] == "pid-1"  # buckets by pipeline_id
        assert kwargs["organization_id"] == "org_x"
        assert kwargs["pipeline_id"] == "pid-1"

    def test_args_identical_on_both_paths(self):
        # The consumer must behave the same regardless of transport — assert the
        # PG-path args equal the Celery-path args.
        celery = MagicMock()
        with patch.object(pd, "resolve_transport", return_value="celery"):
            _dispatch(celery)
        celery_args = celery.send_task.call_args.kwargs["args"]
        celery2 = MagicMock()
        with (
            patch.object(pd, "resolve_transport", return_value="pg_queue"),
            patch.object(pd, "enqueue_task", return_value=1) as enqueue,
        ):
            _dispatch(celery2)
        assert enqueue.call_args.kwargs["args"] == celery_args
