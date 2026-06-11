"""Tests for the PG-queue routing gate (``queue_backend.routing``).

Three layers:

1. **select_backend()** resolves the per-task allow-list correctly,
   defaults to ``CELERY`` when unset, and never raises on malformed
   input.

2. **Observability** — the configured allow-list is logged once, and a
   PG cutover emits a log. These are the gate's only observable effect,
   so they're asserted explicitly (a future "the gate is inert, delete
   it" refactor must fail a test, not pass silently).

3. **dispatch() is inert under routing** — the ``current_app.send_task``
   call is byte-identical whether the routing table selects ``CELERY``
   or ``PG``.
"""

from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest
from queue_backend import QueueBackend, dispatch, select_backend
from queue_backend import routing as routing_mod
from queue_backend.fairness import FairnessKey, WorkloadType
from queue_backend.routing import _ENABLED_TASKS_ENV_VAR as ENABLED_TASKS_ENV

# ``queue_backend.__init__`` binds ``dispatch`` to the *function*, shadowing
# the submodule attribute — import the module explicitly to reach its globals.
dispatch_mod = importlib.import_module("queue_backend.dispatch")


@pytest.fixture(autouse=True)
def _reset_routing_state(monkeypatch):
    """Empty allow-list + cleared log-once guards before each test.

    The allow-list-logged flag and the per-task routing-logged set are
    process-global one-shot guards; reset them so caplog assertions are
    deterministic regardless of test order.
    """
    monkeypatch.delenv(ENABLED_TASKS_ENV, raising=False)
    routing_mod._allow_list_logged = False
    dispatch_mod._pg_routing_logged.clear()
    dispatch_mod._pg_client = None  # drop the process-singleton PG client


# --- select_backend() resolution ---


class TestSelectBackend:
    def test_empty_table_routes_to_celery(self):
        assert select_backend("any_task") is QueueBackend.CELERY

    def test_task_opted_in_routes_to_pg(self, monkeypatch):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "process_log_history")
        assert select_backend("process_log_history") is QueueBackend.PG

    def test_task_not_opted_in_routes_to_celery(self, monkeypatch):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "process_log_history")
        assert select_backend("some_other_task") is QueueBackend.CELERY

    def test_multiple_entries_membership(self, monkeypatch):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "a,b,c")
        assert select_backend("b") is QueueBackend.PG
        assert select_backend("d") is QueueBackend.CELERY


class TestSelectBackendTolerantParsing:
    """Malformed / whitespace input resolves to the safe default, never raises."""

    def test_whitespace_around_entries_trimmed(self, monkeypatch):
        monkeypatch.setenv(ENABLED_TASKS_ENV, " a , b ,  c ")
        assert select_backend("b") is QueueBackend.PG

    def test_empty_and_blank_segments_ignored(self, monkeypatch):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "a,,  ,b")
        assert select_backend("a") is QueueBackend.PG
        # A blank segment must not become a matchable empty-string entry.
        assert select_backend("") is QueueBackend.CELERY

    def test_empty_string_env_routes_to_celery(self, monkeypatch):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "   ")
        assert select_backend("any_task") is QueueBackend.CELERY

    def test_does_not_raise_on_any_input(self, monkeypatch):
        for value in ("", "   ", ",,,", "a,b", "\t\n", ",a,"):
            monkeypatch.setenv(ENABLED_TASKS_ENV, value)
            # Must resolve to an enum member, never raise.
            assert select_backend("a") in (QueueBackend.CELERY, QueueBackend.PG)


class TestQueueBackendEnum:
    def test_string_values(self):
        assert QueueBackend.CELERY == "celery"
        assert QueueBackend.PG == "pg"

    def test_members(self):
        assert {b.value for b in QueueBackend} == {"celery", "pg"}


# --- Observability (the gate's only observable effect) ---


class TestObservability:
    def test_allow_list_logged_once_when_configured(self, monkeypatch, caplog):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "async_execute_bin")
        with caplog.at_level(logging.INFO, logger="queue_backend.routing"):
            select_backend("x")
            select_backend("y")  # second call must NOT re-log
        hits = [r for r in caplog.records if "PG-queue routing enabled" in r.getMessage()]
        assert len(hits) == 1
        assert "async_execute_bin" in hits[0].getMessage()

    def test_empty_allow_list_logs_nothing(self, caplog):
        """Default (feature off) stays silent — truly inert."""
        with caplog.at_level(logging.INFO, logger="queue_backend.routing"):
            select_backend("x")
        assert "PG-queue routing enabled" not in caplog.text


# --- dispatch() routing behaviour (9b: PG-selected enqueues to Postgres) ---


def _mock_pg_client(monkeypatch, *, msg_id=99):
    client = MagicMock()
    client.send.return_value = msg_id
    # Patch on the module object (string target would navigate the shadowing
    # ``dispatch`` *function*, not the submodule).
    monkeypatch.setattr(dispatch_mod, "_get_pg_client", lambda: client)
    return client


class TestDispatchRouting:
    """Celery path unchanged; a PG-selected task enqueues to Postgres, not Celery."""

    def test_celery_path_sends_to_celery_and_never_touches_pg(self):
        with (
            patch("queue_backend.dispatch.current_app") as mock_app,
            patch("queue_backend.dispatch._get_pg_client") as mock_get,
        ):
            dispatch("t1", args=["a"], kwargs={"k": "v"}, queue="general")
        mock_app.send_task.assert_called_once()
        mock_get.assert_not_called()

    def test_pg_selected_enqueues_to_pg_not_celery(self, monkeypatch):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "t1")
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

    def test_pg_default_queue_name_when_unset(self, monkeypatch):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "t1")
        client = _mock_pg_client(monkeypatch)
        dispatch("t1")
        assert client.send.call_args.args[0] == "default"
        # No fairness → org_id None (client coerces to "").
        assert client.send.call_args.kwargs["org_id"] is None


class TestCutoverLog:
    """The PG cutover log: visible (INFO), once per task name."""

    def test_pg_enqueue_logs_once_per_task(self, monkeypatch, caplog):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "t1")
        _mock_pg_client(monkeypatch)
        with caplog.at_level(logging.INFO, logger="queue_backend.dispatch"):
            dispatch("t1")
            dispatch("t1")
            dispatch("t1")
        hits = [r for r in caplog.records if "enqueued to Postgres" in r.getMessage()]
        assert len(hits) == 1

    def test_celery_path_emits_no_pg_log(self, caplog):
        with (
            patch("queue_backend.dispatch.current_app"),
            caplog.at_level(logging.INFO, logger="queue_backend.dispatch"),
        ):
            dispatch("t1")  # empty allow-list → Celery
        assert "enqueued to Postgres" not in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
