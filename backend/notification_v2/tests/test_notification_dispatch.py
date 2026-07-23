"""Unit tests for the buffered-webhook transport routing (UN-3753).

``resolve_transport`` + ``enqueue_task`` are patched on the module, so no Flipt /
DB is needed — these pin the routing contract: PG when the flag resolves PG,
Celery otherwise (fail-closed), with byte-identical args/kwargs/queue on both
paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import notification_v2.notification_dispatch as nd

_ARGS = ["https://hook.test", {"text": "hi"}, {"Content-Type": "application/json"}, 30]
_KWARGS = {
    "max_retries": 3,
    "retry_delay": 10,
    "platform": "SLACK",
    "raise_on_final_failure": True,
    "buffer_row_ids": ["b1", "b2"],
    "organization_id": 7,  # the org pk (worker's buffer-mark contract)
}
_QUEUE = "notifications"


def _dispatch(celery_app, org_string_id="org_x"):
    return nd.dispatch_webhook_notification(
        celery_app=celery_app,
        args=_ARGS,
        kwargs=_KWARGS,
        queue=_QUEUE,
        org_string_id=org_string_id,
    )


class TestDispatchWebhookNotification:
    def test_routes_to_pg_when_flag_resolves_pg(self):
        celery = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="pg_queue"),
            patch.object(nd, "enqueue_task", return_value=42) as enqueue,
        ):
            task_id = _dispatch(celery)
        enqueue.assert_called_once()
        kwargs = enqueue.call_args.kwargs
        assert kwargs["task_name"] == "send_webhook_notification"
        assert kwargs["queue"] == _QUEUE
        assert kwargs["args"] == _ARGS
        assert kwargs["kwargs"] == _KWARGS
        assert kwargs["org_id"] == "org_x"
        # The minted PG task id is returned and threaded into the enqueue row.
        assert kwargs["task_id"] == task_id
        celery.send_task.assert_not_called()

    def test_routes_to_celery_when_flag_resolves_celery(self):
        celery = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="celery"),
            patch.object(nd, "enqueue_task") as enqueue,
        ):
            result = _dispatch(celery)
        celery.send_task.assert_called_once_with(
            "send_webhook_notification", args=_ARGS, kwargs=_KWARGS, queue=_QUEUE
        )
        enqueue.assert_not_called()
        assert result is celery.send_task.return_value.id

    def test_pg_enqueue_failure_propagates_with_no_celery_fallback(self):
        # No silent Celery fallback on PG failure — the caller (_send_clubbed)
        # reverts the buffer rows to PENDING for a clean retry next tick.
        celery = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="pg_queue"),
            patch.object(nd, "enqueue_task", side_effect=RuntimeError("pg down")),
        ):
            with pytest.raises(RuntimeError, match="pg down"):
                _dispatch(celery)
        celery.send_task.assert_not_called()

    def test_none_org_fails_closed_to_celery(self):
        # A missing org string (org deleted) must not route to PG — resolve_transport
        # fails closed, and we pass organization_id=None straight through to it.
        celery = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="celery") as resolve,
            patch.object(nd, "enqueue_task") as enqueue,
        ):
            _dispatch(celery, org_string_id=None)
        assert resolve.call_args.kwargs["organization_id"] is None
        celery.send_task.assert_called_once()
        enqueue.assert_not_called()

    def test_resolve_transport_buckets_by_minted_dispatch_id(self):
        # Fire-and-forget: entity_id is a freshly minted uuid (str), and it equals
        # the PG task_id so the row and the Flipt bucket agree.
        celery = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="pg_queue") as resolve,
            patch.object(nd, "enqueue_task", return_value=1) as enqueue,
        ):
            task_id = _dispatch(celery)
        assert resolve.call_args.kwargs["execution_id"] == task_id
        assert enqueue.call_args.kwargs["task_id"] == task_id

    def test_args_and_kwargs_identical_on_both_paths(self):
        # The consumer must behave the same regardless of transport.
        celery = MagicMock()
        with patch.object(nd, "resolve_transport", return_value="celery"):
            _dispatch(celery)
        celery_call = celery.send_task.call_args.kwargs
        celery2 = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="pg_queue"),
            patch.object(nd, "enqueue_task", return_value=1) as enqueue,
        ):
            _dispatch(celery2)
        assert enqueue.call_args.kwargs["args"] == celery_call["args"]
        assert enqueue.call_args.kwargs["kwargs"] == celery_call["kwargs"]
        assert enqueue.call_args.kwargs["queue"] == celery_call["queue"]
