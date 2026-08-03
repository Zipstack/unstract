"""Unit tests for the buffered-webhook transport routing (UN-3753).

``resolve_transport`` + ``enqueue_task`` are patched on the module, so no Flipt /
DB is needed — these pin the routing contract: PG when the flag resolves PG,
Celery otherwise (fail-closed), with identical args/queue on both paths. The
kwargs are identical EXCEPT two retry-semantics keys forced on the PG branch
(``raise_on_final_failure`` -> False, ``max_retries`` -> 0), because the consumer
runs tasks eagerly via ``apply()`` where the in-task retry loop cannot work — see
``test_pg_forces_terminal_branch_kwargs``.
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
            result = _dispatch(celery)
        task_id = result.task_id
        assert result.transport == nd.PG_TRANSPORT  # rollout metric can tell them apart
        enqueue.assert_called_once()
        kwargs = enqueue.call_args.kwargs
        assert kwargs["task_name"] == "send_webhook_notification"
        assert kwargs["queue"] == _QUEUE
        assert kwargs["args"] == _ARGS
        # Every kwarg is forwarded verbatim EXCEPT the two retry-semantics keys the
        # PG branch forces (see test_pg_forces_terminal_branch_kwargs).
        assert kwargs["kwargs"] == {
            **_KWARGS,
            "raise_on_final_failure": False,
            "max_retries": 0,
        }
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
        assert result.task_id is celery.send_task.return_value.id
        assert result.transport == nd.CELERY_TRANSPORT

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
            task_id = _dispatch(celery).task_id
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
        # kwargs differ ONLY by the two PG-forced retry-semantics keys.
        pg_kwargs = enqueue.call_args.kwargs["kwargs"]
        assert pg_kwargs == {
            **celery_call["kwargs"],
            "raise_on_final_failure": False,
            "max_retries": 0,
        }

    def test_pg_forces_terminal_branch_kwargs(self):
        # Regression (UN-3753): the PG consumer runs the task eagerly via
        # ``task.apply(..., throw=True)``, where the in-task retry loop cannot work:
        #   * max_retries >= 1 -> the worker's ``request.retries < max_retries`` guard
        #     is true on the FIRST failure (retries is always 0 under apply()), so it
        #     raises Retry, which propagates out of apply() -- the terminal branch
        #     (mark DEAD_LETTER + honour raise_on_final_failure) never runs and the row
        #     is left for vt-expiry redelivery, re-POSTing the subscriber each time.
        #   * a terminal re-raise is likewise treated as failure -> redelivery.
        # So the seam must force BOTH max_retries=0 and raise_on_final_failure=False on
        # the PG branch. The Celery branch keeps the caller's values verbatim.
        # (The end-to-end behaviour these kwargs buy — one POST + one dead-letter mark
        # through a real ``task.apply()`` — is asserted in
        # workers/tests/test_notification_pg_terminal.py.)
        assert _KWARGS["raise_on_final_failure"] is True  # guard the fixture premise
        assert _KWARGS["max_retries"] == 3  # ... and that retries are configured
        celery = MagicMock()
        with (
            patch.object(nd, "resolve_transport", return_value="pg_queue"),
            patch.object(nd, "enqueue_task", return_value=1) as enqueue,
        ):
            _dispatch(celery)
        pg_kwargs = enqueue.call_args.kwargs["kwargs"]
        assert pg_kwargs["raise_on_final_failure"] is False
        assert pg_kwargs["max_retries"] == 0
        # The caller's dict is not mutated in place (a fresh dict is enqueued).
        assert _KWARGS["raise_on_final_failure"] is True
        assert _KWARGS["max_retries"] == 3

        celery2 = MagicMock()
        with patch.object(nd, "resolve_transport", return_value="celery"):
            _dispatch(celery2)
        sent_kwargs = celery2.send_task.call_args.kwargs["kwargs"]
        assert sent_kwargs["raise_on_final_failure"] is True
        assert sent_kwargs["max_retries"] == 3
