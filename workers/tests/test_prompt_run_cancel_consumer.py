"""The PG consumer's pre-run cancel check (UN-1031).

This is the only cancel the transport itself can serve: the task has been
claimed but not started, so dropping it costs nothing and spends no LLM
tokens. Everything past this point can only be stopped by the executor's own
checkpoints.

The rules pinned here: a stopped run is dropped and ACKED (never redelivered),
its failure channel still fires so the UI gets a terminal event, and nothing
but an IDE prompt run is ever checked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from celery import shared_task
from queue_backend.pg_queue.client import QueueMessage
from queue_backend.pg_queue.consumer import PgQueueConsumer

from unstract.core.prompt_run_cancellation import PROMPT_RUN_CANCELLED_ERROR

_ran: list = []

# Deliberately NOT named "execute_extraction": the real task claims that name
# in the shared Celery registry as soon as any other test module imports it, and
# the consumer would then run the real body instead of this stub — invisible
# when this file runs alone, a failure in the full suite. The consumer's
# task-name constant is patched to match (see _poll).
_TASK_NAME = "test_prompt_run_cancel.execute_extraction"


@shared_task(name=_TASK_NAME)
def _execute_extraction(context):  # noqa: ANN001 — mirrors the real signature
    _ran.append(context)
    return {"success": True, "data": {}, "metadata": {}}


@pytest.fixture(autouse=True)
def _clear():
    _ran.clear()


def _context(**overrides):
    context = {
        "executor_name": "legacy",
        "operation": "answer_prompt",
        "run_id": "run-1",
        "execution_source": "ide",
        "organization_id": "org-1",
        "executor_params": {},
    }
    context.update(overrides)
    return context


def _payload(context, **overrides):
    payload = {
        "task_name": _TASK_NAME,
        "args": [context],
        "kwargs": {},
        "task_id": "task-1",
        "on_error": {
            "task_name": "ide_prompt_error",
            "args": [],
            "kwargs": {"callback_kwargs": {}},
            "queue": "ide_callback",
        },
    }
    payload.update(overrides)
    return payload


def _msg(payload, msg_id=1):
    return QueueMessage(msg_id=msg_id, message=payload, read_ct=1)


def _poll(payload, *, cancelled: bool):
    client = MagicMock()
    client.read.return_value = [_msg(payload)]
    consumer = PgQueueConsumer(["q"], client=client)
    with (
        patch("queue_backend.pg_queue.consumer._EXECUTE_EXTRACTION_TASK", _TASK_NAME),
        patch(
            "queue_backend.pg_queue.consumer.is_cancelled", return_value=cancelled
        ) as is_cancelled,
        patch.object(consumer, "_fail_dispatch") as fail_dispatch,
    ):
        consumer.poll_once()
    return client, fail_dispatch, is_cancelled


class TestPreRunCancel:
    def test_cancelled_run_is_not_executed(self):
        _, _, _ = _poll(_payload(_context()), cancelled=True)
        assert _ran == []  # no LLM spend

    def test_cancelled_run_is_acked_not_redelivered(self):
        client, _, _ = _poll(_payload(_context()), cancelled=True)
        # Redelivery would re-run the task the user just stopped.
        client.delete.assert_called_once_with(1)

    def test_cancelled_run_surfaces_the_sentinel_on_its_failure_channel(self):
        # The continuations live IN the payload and die with the row, so the
        # UI only learns the run ended if we fire on_error ourselves.
        _, fail_dispatch, _ = _poll(_payload(_context()), cancelled=True)
        fail_dispatch.assert_called_once()
        assert fail_dispatch.call_args.kwargs["error"] == PROMPT_RUN_CANCELLED_ERROR

    def test_uncancelled_run_executes_normally(self):
        _, fail_dispatch, _ = _poll(_payload(_context()), cancelled=False)
        assert len(_ran) == 1
        fail_dispatch.assert_not_called()

    def test_checks_the_run_against_its_own_org(self):
        _, _, is_cancelled = _poll(
            _payload(_context(organization_id="org-9", run_id="run-9")),
            cancelled=False,
        )
        is_cancelled.assert_called_once_with("org-9", "run-9")


class TestScope:
    """Everything that is NOT an IDE prompt run must skip the lookup entirely —
    the workflow fleet's traffic must not pay a signal-store round trip.
    """

    def test_workflow_runs_are_not_checked(self):
        _, _, is_cancelled = _poll(
            _payload(_context(execution_source="tool")), cancelled=True
        )
        is_cancelled.assert_not_called()
        assert len(_ran) == 1  # ran despite the cancel flag being set

    def test_other_tasks_are_not_checked(self):
        payload = _payload(_context(), task_name="test_pg_consumer.ok")
        client = MagicMock()
        client.read.return_value = [_msg(payload)]
        with (
            patch("queue_backend.pg_queue.consumer._EXECUTE_EXTRACTION_TASK", _TASK_NAME),
            patch(
                "queue_backend.pg_queue.consumer.is_cancelled", return_value=True
            ) as is_cancelled,
        ):
            PgQueueConsumer(["q"], client=client).poll_once()
        is_cancelled.assert_not_called()

    def test_missing_run_id_is_not_checked(self):
        _, _, is_cancelled = _poll(_payload(_context(run_id="")), cancelled=True)
        is_cancelled.assert_not_called()
        assert len(_ran) == 1

    def test_malformed_args_do_not_raise(self):
        _, _, is_cancelled = _poll(_payload(None, args=["not-a-dict"]), cancelled=True)
        is_cancelled.assert_not_called()
