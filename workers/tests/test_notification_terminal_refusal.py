"""A webhook refusal no retry can clear must not be retried.

``send_webhook_notification`` dead-letters the buffer rows the moment the sink
reports ``retryable: False``, then honours ``raise_on_final_failure``. That
raise happens inside the task's own ``try``, so a plain ``Exception`` was
caught by the broad handler below it and fed straight back into
``self.retry(...)`` — the URL got re-resolved up to ``max_retries`` times and
``_mark_buffer_outcome(dispatched=False)`` ran a second time on exhaustion.

``TerminalWebhookRefusal`` exists to cross that handler untouched. These tests
pin the behaviour rather than the mechanism: one POST, one dead-letter mark,
and no ``Retry``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from notification.tasks import TerminalWebhookRefusal, send_webhook_notification

_URL = "https://127.0.0.1/hook"
_BUFFER_IDS = ["b1", "b2"]
_ORG = 7


class _RefusingProvider:
    """Stands in for the sink refusing a URL that can never be dialled."""

    def __init__(self, *, retryable: bool) -> None:
        self.posts = 0
        self._retryable = retryable

    def send(self, notification_data: dict) -> dict:
        self.posts += 1
        return {
            "success": False,
            "message": "Webhook URL is not an allowed public destination",
            "details": {"retryable": self._retryable},
        }


def _run(*, retryable: bool, max_retries: int, raise_on_final_failure: bool):
    provider = _RefusingProvider(retryable=retryable)
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
        except BaseException as exc:  # noqa: BLE001 - the type is the assertion
            raised = exc
    return provider, marks, raised


def test_terminal_refusal_is_not_retried_when_it_must_raise():
    # raise_on_final_failure=True with retries left is the case that regressed:
    # the raise has to reach the caller as a FAILURE, not loop back into retry.
    provider, marks, raised = _run(
        retryable=False, max_retries=3, raise_on_final_failure=True
    )
    assert isinstance(raised, TerminalWebhookRefusal)
    assert not isinstance(raised, Retry)
    assert provider.posts == 1  # the URL is resolved once, not max_retries times
    assert marks == [False]  # dead-lettered exactly once


def test_terminal_refusal_without_raise_returns_quietly():
    provider, marks, raised = _run(
        retryable=False, max_retries=3, raise_on_final_failure=False
    )
    assert raised is None
    assert provider.posts == 1
    assert marks == [False]


@pytest.mark.parametrize("raise_on_final", [True, False])
def test_a_retryable_failure_still_retries(raise_on_final):
    """The fast path must not swallow a resolver outage, which can clear."""
    provider, marks, raised = _run(
        retryable=True, max_retries=3, raise_on_final_failure=raise_on_final
    )
    assert isinstance(raised, Retry)
    assert marks == []  # not dead-lettered while attempts remain
