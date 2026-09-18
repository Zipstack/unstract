"""Tests for queue-transport routing and ``dispatch()`` (UN-4046).

PG is the only transport: ``select_backend()`` returns ``PG`` unconditionally and
``dispatch()`` enqueues to Postgres. What these pin is the *payload* the PG
consumer receives, the no-silent-fallback contract, and the per-thread client
reuse.

The allow-list suites are gone with ``WORKER_PG_QUEUE_ENABLED_TASKS`` — the
parsing, the tolerant-whitespace cases, the "logged once when configured"
observability and every "celery path" case describe a gate that no longer exists.
"""

from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest
from queue_backend import QueueBackend, dispatch, select_backend
from queue_backend.fairness import FairnessKey, WorkloadType

# ``queue_backend.__init__`` binds ``dispatch`` to the *function*, shadowing
# the submodule attribute — import the module explicitly to reach its globals.
dispatch_mod = importlib.import_module("queue_backend.dispatch")


@pytest.fixture(autouse=True)
def _reset_routing_state():
    """Clear the log-once guard and the per-thread PG client before each test.

    The per-task routing-logged set is a process-global one-shot guard; reset it
    so caplog assertions are deterministic regardless of test order.
    """
    dispatch_mod._pg_routing_logged.clear()
    dispatch_mod._pg_local.client = None


def _mock_pg_client(monkeypatch, *, msg_id=99):
    client = MagicMock()
    client.send.return_value = msg_id
    # Patch on the module object (string target would navigate the shadowing
    # ``dispatch`` *function*, not the submodule).
    monkeypatch.setattr(dispatch_mod, "_get_pg_client", lambda: client)
    return client


class TestSelectBackend:
    def test_always_pg(self):
        # No argument since UN-4046 — the task name never mattered once the
        # allow-list went, and Sonar flagged it as an unused parameter.
        assert select_backend() is QueueBackend.PG


class TestQueueBackendEnum:
    def test_string_values(self):
        assert QueueBackend.CELERY == "celery"
        assert QueueBackend.PG == "pg"

    def test_members(self):
        assert {b.value for b in QueueBackend} == {"celery", "pg"}


class TestDispatchRouting:
    """A dispatch enqueues to Postgres and never touches Celery."""

    def test_enqueues_to_pg_not_celery(self, monkeypatch):
        client = _mock_pg_client(monkeypatch, msg_id=99)
        fairness = FairnessKey(org_id="org-1", workload_type=WorkloadType.API)
        with patch("queue_backend.dispatch.current_app") as mock_app:
            handle = dispatch(
                "t1", args=["a", 1], kwargs={"k": "v"}, queue="general", fairness=fairness
            )
        mock_app.send_task.assert_not_called()
        client.send.assert_called_once()
        queue_name, message = client.send.call_args.args
        assert queue_name == "general"
        assert message["task_name"] == "t1"
        assert message["args"] == ["a", 1]
        assert message["kwargs"] == {"k": "v"}
        assert message["queue"] == "general"
        assert message["fairness"]["org_id"] == "org-1"
        assert client.send.call_args.kwargs["org_id"] == "org-1"
        # Handle satisfies TaskHandle (.id) and carries the msg_id.
        assert handle.id == "99"

    def test_default_queue_name_when_unset(self, monkeypatch):
        client = _mock_pg_client(monkeypatch)
        dispatch("t1")
        assert client.send.call_args.args[0] == "default"
        # No fairness → org_id None (client coerces to "").
        assert client.send.call_args.kwargs["org_id"] is None

    def test_enqueue_failure_propagates_and_does_not_fall_back(self, monkeypatch):
        """A PG enqueue failure raises — no silent Celery fallback."""
        client = MagicMock()
        client.send.side_effect = RuntimeError("db down")
        monkeypatch.setattr(dispatch_mod, "_get_pg_client", lambda: client)
        with (
            patch("queue_backend.dispatch.current_app") as mock_app,
            pytest.raises(RuntimeError),
        ):
            dispatch("t1")
        mock_app.send_task.assert_not_called()  # never falls back to Celery
        # The routing decision is logged BEFORE the send, so even a failing
        # first dispatch announced it (pins the log-ordering property).
        assert "t1" in dispatch_mod._pg_routing_logged

    def test_get_pg_client_lazily_inits_and_reuses(self, monkeypatch):
        """The per-thread client is constructed once and reused (connection reuse)."""
        dispatch_mod._pg_local.client = None
        sentinel = object()
        ctor = MagicMock(return_value=sentinel)
        monkeypatch.setattr(dispatch_mod, "PgQueueClient", ctor)
        assert dispatch_mod._get_pg_client() is sentinel
        assert dispatch_mod._get_pg_client() is sentinel
        ctor.assert_called_once()


class TestCutoverLog:
    """The PG routing log: visible (INFO), once per task name."""

    def test_pg_enqueue_logs_once_per_task(self, monkeypatch, caplog):
        _mock_pg_client(monkeypatch)
        with caplog.at_level(logging.INFO, logger="queue_backend.dispatch"):
            dispatch("t1")
            dispatch("t1")
            dispatch("t1")
        hits = [r for r in caplog.records if "routing task=" in r.getMessage()]
        assert len(hits) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
