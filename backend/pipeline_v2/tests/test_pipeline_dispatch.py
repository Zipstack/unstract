"""Unit tests for the API-triggered pipeline-trigger transport routing (UN-3616).

`resolve_transport` + `enqueue_task` are patched on the module, so no Flipt / DB
is needed — these pin the routing contract: PG when the flag resolves PG, Celery
otherwise (fail-closed), with byte-identical args on both paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
            transport = _dispatch(celery)
        assert transport == "pg_queue"
        enqueue.assert_called_once()
        kwargs = enqueue.call_args.kwargs
        assert kwargs["task_name"] == "scheduler.tasks.execute_pipeline_task"
        assert kwargs["queue"] == "scheduler"
        assert kwargs["args"] == _EXPECTED_ARGS
        assert kwargs["org_id"] == "org_x"
        celery.send_task.assert_not_called()

    def test_routes_to_celery_when_flag_resolves_celery(self):
        celery = MagicMock()
        with (
            patch.object(pd, "resolve_transport", return_value="celery"),
            patch.object(pd, "enqueue_task") as enqueue,
        ):
            transport = _dispatch(celery)
        assert transport == "celery"
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
