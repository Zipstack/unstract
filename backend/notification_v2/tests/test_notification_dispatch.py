"""Unit tests for the buffered-webhook transport routing (UN-3753).

``resolve_transport`` + ``enqueue_task`` are patched on the module, so no Flipt /
DB is needed — these pin the routing contract: PG when the flag resolves PG,
Celery otherwise (fail-closed), with identical args/queue on both paths. The
kwargs are identical EXCEPT ``raise_on_final_failure``, which is forced ``False``
on the PG branch (the re-raise means "redeliver" on PG, not "dead-letter" — see
``test_pg_forces_raise_on_final_failure_false``).
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
        # Every kwarg is forwarded verbatim EXCEPT raise_on_final_failure, which the
        # PG branch forces False (see test_pg_forces_raise_on_final_failure_false).
        assert kwargs["kwargs"] == {**_KWARGS, "raise_on_final_failure": False}
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
        # No silent Celery fallback on a TRANSIENT PG failure — it propagates raw
        # (not wrapped), so the caller (_send_clubbed) reverts rows to PENDING.
        celery = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="pg_queue"),
            patch.object(nd, "enqueue_task", side_effect=RuntimeError("pg down")),
        ):
            with pytest.raises(RuntimeError, match="pg down"):
                _dispatch(celery)
        celery.send_task.assert_not_called()

    def test_pg_permanent_enqueue_error_is_wrapped(self):
        # A PERMANENT enqueue error (ValueError/TypeError: validation / JSON encode)
        # is re-raised as PermanentDispatchError so the caller dead-letters it —
        # raised ONLY on the PG path, so the Celery flow is never affected.
        celery = MagicMock()
        for exc in (ValueError("priority out of range"), TypeError("not serializable")):
            with (
                patch.object(nd, "resolve_transport", return_value="pg_queue"),
                patch.object(nd, "enqueue_task", side_effect=exc),
            ):
                with pytest.raises(nd.PermanentDispatchError):
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

    def test_args_and_queue_identical_on_both_paths(self):
        # The consumer must behave the same regardless of transport — args/queue are
        # byte-identical, and kwargs match apart from the transport-specific
        # raise_on_final_failure override (asserted separately below).
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
        assert enqueue.call_args.kwargs["queue"] == celery_call["queue"]
        # kwargs differ ONLY by the PG-forced raise_on_final_failure flag.
        pg_kwargs = enqueue.call_args.kwargs["kwargs"]
        assert pg_kwargs == {**celery_call["kwargs"], "raise_on_final_failure": False}

    def test_pg_forces_raise_on_final_failure_false(self):
        # Regression (UN-3753): on the PG consumer a re-raise on retry exhaustion
        # leaves the row for vt-expiry redelivery — the subscriber would be re-POSTed
        # up to max_attempts times AND a false poison-drop would be logged. The
        # dispatch seam must override raise_on_final_failure -> False on the PG branch
        # (worker already marks buffers DEAD_LETTER directly) so the task returns None
        # -> the consumer acks -> the endpoint is hit once, matching Celery's external
        # behaviour. The Celery branch keeps the caller's True verbatim.
        assert _KWARGS["raise_on_final_failure"] is True  # guard the fixture premise
        celery = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="pg_queue"),
            patch.object(nd, "enqueue_task", return_value=1) as enqueue,
        ):
            _dispatch(celery)
        assert enqueue.call_args.kwargs["kwargs"]["raise_on_final_failure"] is False
        # The caller's dict is not mutated in place (a fresh dict is enqueued).
        assert _KWARGS["raise_on_final_failure"] is True

        celery2 = MagicMock()
        with patch.object(nd, "resolve_transport", return_value="celery"):
            _dispatch(celery2)
        sent_kwargs = celery2.send_task.call_args.kwargs["kwargs"]
        assert sent_kwargs["raise_on_final_failure"] is True
