"""``send_webhook_notification`` under the PG consumer's eager ``task.apply()``.

The PG consumer runs tasks with ``task.apply(..., throw=True)`` rather than through
a Celery worker. Under ``apply()`` Celery's in-task retry loop cannot work —
``self.request.retries`` is ALWAYS 0, so the task's
``if self.request.retries < max_retries`` guard is true on the FIRST failure for any
``max_retries >= 1`` and raises ``Retry``, which ``throw=True`` propagates straight
out of ``apply()``. The terminal branch (mark buffers DEAD_LETTER, honour
``raise_on_final_failure``) is then never reached, so the consumer sees an exception,
leaves the row for vt-expiry redelivery, and the subscriber is re-POSTed every time.

That is why the dispatch seam (``backend/notification_v2/notification_dispatch.py``)
forces BOTH ``max_retries=0`` and ``raise_on_final_failure=False`` on the PG branch.
These tests drive the REAL task through ``apply()`` and assert the behaviour those
kwargs buy — one POST + one DEAD_LETTER mark, no raise — rather than the kwarg values
(which the seam's own unit tests already pin).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from notification.tasks import send_webhook_notification

_URL = "https://hook.test/x"
_BUFFER_IDS = ["b1", "b2"]
_ORG = 7


class _AlwaysFailingProvider:
    """Webhook provider whose send() always reports failure, counting attempts."""

    def __init__(self) -> None:
        self.posts = 0

    def send(self, notification_data: dict) -> dict:
        self.posts += 1
        return {"success": False, "message": "boom"}


def _run(*, max_retries: int, raise_on_final_failure: bool):
    """Drive the real task through the consumer's exact call shape.

    Returns ``(provider, marks, raised)`` — POST count, the
    ``_mark_buffer_outcome`` calls, and any exception propagated out of apply().
    """
    provider = _AlwaysFailingProvider()
    marks: list[bool] = []
    with (
        patch(
            "notification.tasks._get_webhook_provider_for_url", return_value=provider
        ),
        patch(
            "notification.tasks._mark_buffer_outcome",
            side_effect=lambda ids, org, *, dispatched: marks.append(dispatched),
        ),
    ):
        raised: BaseException | None = None
        try:
            send_webhook_notification.apply(
                args=[_URL, {"text": "hi"}, {"Content-Type": "application/json"}, 30],
                kwargs={
                    "max_retries": max_retries,
                    "retry_delay": 10,
                    "platform": None,
                    "raise_on_final_failure": raise_on_final_failure,
                    "buffer_row_ids": _BUFFER_IDS,
                    "organization_id": _ORG,
                },
                throw=True,
            )
        except BaseException as exc:  # noqa: BLE001 - we assert on the type below
            raised = exc
    return provider, marks, raised


def test_pg_kwargs_give_one_post_and_one_dead_letter():
    # The seam's PG kwargs (max_retries=0, raise_on_final_failure=False): the task
    # takes the terminal branch on the first failure, marks the buffers DEAD_LETTER,
    # and returns None -> the consumer acks the row. Subscriber hit exactly once.
    provider, marks, raised = _run(max_retries=0, raise_on_final_failure=False)
    assert raised is None  # nothing propagates -> consumer acks (no redelivery)
    assert provider.posts == 1  # subscriber POSTed once, not once per redelivery
    assert marks == [False]  # exactly one DEAD_LETTER mark


def test_unforced_max_retries_would_escape_apply_without_dead_lettering():
    # Regression guard for the bug the override fixes: with the caller's original
    # max_retries >= 1, apply() raises Retry out of the task, the terminal branch
    # never runs, and NO buffer mark happens -> the consumer would redeliver and
    # re-POST. This is what the seam prevents by forcing max_retries=0.
    provider, marks, raised = _run(max_retries=3, raise_on_final_failure=False)
    assert isinstance(raised, Retry)  # escapes apply() as an exception
    assert provider.posts == 1  # ... after a single POST on this delivery
    assert marks == []  # buffers NEVER dead-lettered -> rows strand/redeliver


@pytest.mark.parametrize("raise_on_final", [True, False])
def test_max_retries_zero_always_reaches_terminal_branch(raise_on_final):
    # With max_retries=0 the terminal branch always runs, so the buffers are marked
    # DEAD_LETTER regardless of raise_on_final_failure; the flag only decides whether
    # the task additionally re-raises (a Celery FAILURE-state signal).
    provider, marks, raised = _run(
        max_retries=0, raise_on_final_failure=raise_on_final
    )
    assert provider.posts == 1
    assert marks == [False]  # dead-lettered on BOTH transports, before any re-raise
    assert (raised is not None) is raise_on_final
