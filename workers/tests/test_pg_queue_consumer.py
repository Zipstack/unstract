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


def _msg(msg_id, payload):
    return QueueMessage(msg_id=msg_id, message=payload)


# --- poll_once (mocked client, real tasks) ---


class TestPollOnce:
    def test_runs_task_and_acks(self):
        client = MagicMock()
        client.read.return_value = [
            _msg(1, {"task_name": "test_pg_consumer.ok", "args": [3], "kwargs": {"y": 4}})
        ]
        assert PgQueueConsumer("q", client=client).poll_once() == 1
        assert _calls == [(3, 4)]  # task body ran
        client.delete.assert_called_once_with(1)  # acked

    def test_failed_task_is_not_acked(self):
        client = MagicMock()
        client.read.return_value = [
            _msg(2, {"task_name": "test_pg_consumer.boom", "args": [], "kwargs": {}})
        ]
        PgQueueConsumer("q", client=client).poll_once()
        client.delete.assert_not_called()  # left for vt-expiry redelivery

    def test_unknown_task_is_dropped(self, caplog):
        client = MagicMock()
        client.read.return_value = [
            _msg(3, {"task_name": "nope.nope", "args": [], "kwargs": {}})
        ]
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer("q", client=client).poll_once()
        client.delete.assert_called_once_with(3)  # dropped, not redelivered
        assert "unknown task" in caplog.text

    def test_empty_batch_acks_nothing(self):
        client = MagicMock()
        client.read.return_value = []
        assert PgQueueConsumer("q", client=client).poll_once() == 0
        client.delete.assert_not_called()


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
