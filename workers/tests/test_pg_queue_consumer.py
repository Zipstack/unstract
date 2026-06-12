"""Tests for the PG queue consumer (claim → run → ack).

Unit tests drive ``poll_once`` with a mocked client and *real* registered
Celery tasks (so ``apply()`` actually runs the body). The integration test
exercises the full enqueue → poll → execute → ack loop against real Postgres
(skips if unreachable / unmigrated).
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock

import pytest
from celery import shared_task
from queue_backend.fairness import FAIRNESS_HEADER_NAME
from queue_backend.pg_queue import to_payload
from queue_backend.pg_queue.client import QueueMessage
from queue_backend.pg_queue.consumer import PgQueueConsumer

# Registered test tasks (namespaced). apply() runs their bodies in-process.
_calls: list = []


@shared_task(name="test_pg_consumer.ok")
def _ok_task(x, y=0):
    _calls.append((x, y))
    return x + y


@shared_task(name="test_pg_consumer.boom")
def _boom_task():
    raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _clear_calls():
    _calls.clear()


def _msg(msg_id, payload, *, read_ct=1):
    return QueueMessage(msg_id=msg_id, message=payload, read_ct=read_ct)


def _ok_payload(x, y=0):
    return {"task_name": "test_pg_consumer.ok", "args": [x], "kwargs": {"y": y}}


# --- poll_once (mocked client, real tasks) ---


class TestPollOnce:
    def test_runs_task_and_acks(self):
        client = MagicMock()
        client.read.return_value = [_msg(1, _ok_payload(3, 4))]
        assert PgQueueConsumer("q", client=client).poll_once() == 1
        assert _calls == [(3, 4)]  # task body ran
        client.delete.assert_called_once_with(1)  # acked

    def test_failed_task_is_not_acked_and_logs(self, caplog):
        client = MagicMock()
        client.read.return_value = [
            _msg(2, {"task_name": "test_pg_consumer.boom", "args": [], "kwargs": {}})
        ]
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer("q", client=client).poll_once()
        client.delete.assert_not_called()  # left for vt-expiry redelivery
        assert "failed" in caplog.text  # the cycling signal is logged

    def test_unknown_task_is_dropped(self, caplog):
        client = MagicMock()
        client.read.return_value = [
            _msg(3, {"task_name": "nope.nope", "args": [], "kwargs": {}})
        ]
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer("q", client=client).poll_once()
        client.delete.assert_called_once_with(3)  # dropped, not redelivered
        assert "unknown task" in caplog.text

    def test_missing_task_name_dropped_as_malformed(self, caplog):
        client = MagicMock()
        client.read.return_value = [_msg(4, {"args": [], "kwargs": {}})]  # no task_name
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer("q", client=client).poll_once()
        client.delete.assert_called_once_with(4)
        assert "missing task_name" in caplog.text  # distinct from "unknown task"

    def test_poison_message_dropped_past_max_attempts(self, caplog):
        client = MagicMock()
        # boom task, claimed more than max_attempts times → drop instead of redeliver.
        client.read.return_value = [
            _msg(5, {"task_name": "test_pg_consumer.boom"}, read_ct=6)
        ]
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer("q", client=client, max_attempts=5).poll_once()
        client.delete.assert_called_once_with(5)  # dropped as poison
        assert "poison" in caplog.text

    def test_fairness_header_rebuilt_for_run(self):
        # Mock app so we can inspect the apply() headers.
        fairness = {"org_id": "o", "workload_type": "api", "pipeline_priority": 5}
        task = MagicMock()
        app = MagicMock()
        app.tasks.get.return_value = task
        client = MagicMock()
        client.read.return_value = [
            _msg(6, {"task_name": "t", "args": [1], "kwargs": {"k": "v"}, "fairness": fairness})
        ]
        PgQueueConsumer("q", client=client, app=app).poll_once()
        kwargs = task.apply.call_args.kwargs
        assert kwargs["args"] == [1]
        assert kwargs["kwargs"] == {"k": "v"}
        assert kwargs["headers"] == {FAIRNESS_HEADER_NAME: fairness}

    def test_ack_finding_no_row_warns(self, caplog):
        client = MagicMock()
        client.delete.return_value = False  # row already gone (vt expired mid-run)
        client.read.return_value = [_msg(7, _ok_payload(1))]
        with caplog.at_level(logging.WARNING, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer("q", client=client).poll_once()
        assert "possible double-run" in caplog.text

    def test_multi_message_batch(self):
        client = MagicMock()
        client.read.return_value = [
            _msg(10, _ok_payload(1)),
            _msg(11, {"task_name": "test_pg_consumer.boom"}),
            _msg(12, {"task_name": "nope.nope"}),
            _msg(13, _ok_payload(2)),
        ]
        assert PgQueueConsumer("q", client=client).poll_once() == 4
        assert _calls == [(1, 0), (2, 0)]  # ok tasks ran in order
        deleted = {c.args[0] for c in client.delete.call_args_list}
        assert deleted == {10, 12, 13}  # ok acked + unknown dropped; boom NOT acked

    def test_empty_batch_acks_nothing(self):
        client = MagicMock()
        client.read.return_value = []
        assert PgQueueConsumer("q", client=client).poll_once() == 0
        client.delete.assert_not_called()


class TestConstruction:
    def test_rejects_non_positive_params(self):
        for kw in (
            {"batch_size": 0},
            {"vt_seconds": -1},
            {"poll_interval": 0},
            {"backoff_max": 0},
            {"max_attempts": 0},
        ):
            with pytest.raises(ValueError):
                PgQueueConsumer("q", client=MagicMock(), **kw)


class TestRunLoop:
    def test_run_stops_gracefully(self, monkeypatch):
        client = MagicMock()
        client.read.return_value = []  # always empty → backoff path
        consumer = PgQueueConsumer("q", client=client)
        # First empty poll → sleep (patched to request stop) → loop exits.
        monkeypatch.setattr(
            "queue_backend.pg_queue.consumer.time.sleep", lambda _s: consumer.stop()
        )
        consumer.run(install_signals=False)
        assert consumer._running is False

    def test_backoff_grows_then_resets(self, monkeypatch):
        client = MagicMock()
        # empty, empty, one message, empty → backoff doubles, resets, doubles.
        client.read.side_effect = [[], [], [_msg(1, _ok_payload(1))], []]
        consumer = PgQueueConsumer(
            "q", client=client, poll_interval=0.1, backoff_max=0.25
        )
        sleeps: list[float] = []

        def _sleep(secs):
            sleeps.append(secs)
            if len(sleeps) == 3:  # stop after the third sleep
                consumer.stop()

        monkeypatch.setattr("queue_backend.pg_queue.consumer.time.sleep", _sleep)
        consumer.run(install_signals=False)
        # empty→0.1, empty→0.2 (doubled), [msg] resets, empty→0.1 again.
        assert sleeps == [0.1, 0.2, 0.1]

    def test_poll_error_does_not_kill_loop(self, monkeypatch):
        client = MagicMock()
        # first poll raises (transient), then empty → loop must survive the raise.
        client.read.side_effect = [RuntimeError("blip"), []]
        consumer = PgQueueConsumer("q", client=client)
        sleeps: list[float] = []

        def _sleep(secs):
            sleeps.append(secs)
            if len(sleeps) == 2:  # stop after the post-error poll
                consumer.stop()

        monkeypatch.setattr("queue_backend.pg_queue.consumer.time.sleep", _sleep)
        consumer.run(install_signals=False)  # must not raise
        assert client.read.call_count == 2  # kept polling after the error


# --- Integration: full enqueue → poll → execute → ack against real PG ---
# Uses the shared ``pg_client`` fixture from conftest.py.


class TestConsumerIntegration:
    def test_enqueue_poll_execute_ack(self, pg_client):
        queue_name = f"test_consumer_{os.getpid()}"
        try:
            pg_client.send(
                queue_name,
                to_payload("test_pg_consumer.ok", args=[5], kwargs={"y": 6}),
            )
            claimed = PgQueueConsumer(queue_name, client=pg_client).poll_once()
            assert claimed == 1
            assert (5, 6) in _calls  # task actually executed off Postgres
            # Row was acked (deleted) — nothing left to claim.
            assert pg_client.read(queue_name, vt_seconds=30, qty=10) == []
        finally:
            with pg_client.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM pg_queue_message WHERE queue_name = %s", (queue_name,)
                )
            pg_client.conn.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
