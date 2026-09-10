"""Unit tests for the buffered-webhook PG dispatch (UN-3753, UN-4046).

``enqueue_task`` is patched on the module, so no DB is needed. These pin the
payload contract the notification consumer depends on, the permanent-vs-transient
error split the caller branches on, and the two retry-semantics kwargs the seam
forces because the consumer runs tasks eagerly via ``apply()``.

The transport-routing tests went with the ``pg_queue_enabled`` flag (UN-4046) —
"routes to celery", "fails closed to celery on a missing org", "buckets by minted
dispatch id" and "identical on both paths" no longer describe anything. What the
missing-org case still asserts (the row carries an empty org id rather than
``None``) is kept below, because ``enqueue_task`` types ``org_id`` as ``str``.
"""

from __future__ import annotations

from unittest.mock import patch

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


def _dispatch(org_string_id="org_x"):
    return nd.dispatch_webhook_notification(
        args=_ARGS,
        kwargs=_KWARGS,
        queue=_QUEUE,
        org_string_id=org_string_id,
    )


class TestDispatchWebhookNotification:
    def test_enqueues_with_the_consumer_payload_contract(self):
        with patch.object(nd, "enqueue_task", return_value=42) as enqueue:
            task_id = _dispatch()
        enqueue.assert_called_once()
        kwargs = enqueue.call_args.kwargs
        assert kwargs["task_name"] == "send_webhook_notification"
        assert kwargs["queue"] == _QUEUE
        assert kwargs["args"] == _ARGS
        # Every kwarg forwarded verbatim EXCEPT the two retry-semantics keys the
        # seam forces (see test_forces_terminal_branch_kwargs).
        assert kwargs["kwargs"] == {
            **_KWARGS,
            "raise_on_final_failure": False,
            "max_retries": 0,
        }
        assert kwargs["org_id"] == "org_x"
        # The minted PG task id is returned and threaded into the enqueue row.
        assert kwargs["task_id"] == task_id

    def test_transient_enqueue_failure_propagates_raw(self):
        # A TRANSIENT PG failure propagates unwrapped, so the caller (_send_clubbed)
        # reverts the rows to PENDING rather than dead-lettering them.
        with patch.object(nd, "enqueue_task", side_effect=RuntimeError("pg down")):
            with pytest.raises(RuntimeError, match="pg down"):
                _dispatch()

    def test_permanent_enqueue_error_is_wrapped(self):
        # A PERMANENT enqueue error (ValueError/TypeError: validation / JSON encode)
        # is re-raised as PermanentDispatchError so the caller dead-letters it
        # instead of retrying something that will fail identically every time.
        for exc in (ValueError("priority out of range"), TypeError("not serializable")):
            with patch.object(nd, "enqueue_task", side_effect=exc):
                with pytest.raises(nd.PermanentDispatchError):
                    _dispatch()

    def test_none_org_is_coerced_to_empty_string_on_the_row(self):
        # enqueue_task types org_id as str; a deleted org must not put None on the
        # row. (The producer re-coerces too, so this pins the seam's own contract.)
        with patch.object(nd, "enqueue_task", return_value=1) as enqueue:
            _dispatch(org_string_id=None)
        assert enqueue.call_args.kwargs["org_id"] == ""

    def test_forces_terminal_branch_kwargs(self):
        # Regression (UN-3753): the PG consumer runs the task eagerly via
        # ``task.apply(..., throw=True)``, where the in-task retry loop cannot work:
        #   * max_retries >= 1 -> the worker's ``request.retries < max_retries`` guard
        #     is true on the FIRST failure (retries is always 0 under apply()), so it
        #     raises Retry, which propagates out of apply() -- the terminal branch
        #     (mark DEAD_LETTER + honour raise_on_final_failure) never runs and the row
        #     is left for vt-expiry redelivery, re-POSTing the subscriber each time.
        #   * a terminal re-raise is likewise treated as failure -> redelivery.
        # So the seam must force BOTH max_retries=0 and raise_on_final_failure=False.
        # (The end-to-end behaviour these kwargs buy — one POST + one dead-letter mark
        # through a real ``task.apply()`` — is asserted in
        # workers/tests/test_notification_pg_terminal.py.)
        assert _KWARGS["raise_on_final_failure"] is True  # guard the fixture premise
        assert _KWARGS["max_retries"] == 3  # ... and that retries are configured
        with patch.object(nd, "enqueue_task", return_value=1) as enqueue:
            _dispatch()
        pg_kwargs = enqueue.call_args.kwargs["kwargs"]
        assert pg_kwargs["raise_on_final_failure"] is False
        assert pg_kwargs["max_retries"] == 0
        # The caller's dict is not mutated in place (a fresh dict is enqueued).
        assert _KWARGS["raise_on_final_failure"] is True
        assert _KWARGS["max_retries"] == 3
