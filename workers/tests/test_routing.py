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
from unittest.mock import patch

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

    def test_pg_selection_emits_routing_log(self, monkeypatch, caplog):
        """Pins the dispatch() routing branch: deleting it must fail here."""
        monkeypatch.setenv(ENABLED_TASKS_ENV, "t1")
        with (
            patch("queue_backend.dispatch.current_app"),
            caplog.at_level(logging.INFO, logger="queue_backend.dispatch"),
        ):
            dispatch("t1")
        assert "PG-queue routing selected" in caplog.text

    def test_celery_selection_emits_no_routing_log(self, caplog):
        """Negative case — guards against the gate being made unconditional."""
        with (
            patch("queue_backend.dispatch.current_app"),
            caplog.at_level(logging.INFO, logger="queue_backend.dispatch"),
        ):
            dispatch("t1")  # empty allow-list → CELERY
        assert "PG-queue routing selected" not in caplog.text

    def test_routing_log_bounded_to_once_per_task(self, monkeypatch, caplog):
        monkeypatch.setenv(ENABLED_TASKS_ENV, "t1")
        with (
            patch("queue_backend.dispatch.current_app"),
            caplog.at_level(logging.INFO, logger="queue_backend.dispatch"),
        ):
            dispatch("t1")
            dispatch("t1")
            dispatch("t1")
        hits = [r for r in caplog.records if "PG-queue routing selected" in r.getMessage()]
        assert len(hits) == 1


# --- dispatch() is inert under routing (the scaffold invariant) ---


class TestDispatchByteIdenticalRegardlessOfRouting:
    """``dispatch()`` produces the same send_task call whether routed PG or Celery."""

    def _capture_send_task(self, task_name, fairness):
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch(
                task_name,
                args=["a", 1],
                kwargs={"k": "v"},
                queue="general",
                fairness=fairness,
            )
        return mock_app.send_task.call_args

    def test_pg_selection_does_not_change_the_wire(self, monkeypatch):
        fairness = FairnessKey(org_id="org-1", workload_type=WorkloadType.API)

        # Celery path (empty table).
        celery_call = self._capture_send_task("t1", fairness)

        # PG path (task opted in) — same inputs.
        monkeypatch.setenv(ENABLED_TASKS_ENV, "t1")
        pg_call = self._capture_send_task("t1", fairness)

        assert celery_call == pg_call
        assert pg_call.args[0] == "t1"
        assert pg_call.kwargs["args"] == ["a", 1]
        assert pg_call.kwargs["kwargs"] == {"k": "v"}
        assert pg_call.kwargs["queue"] == "general"

    def test_dispatch_without_fairness_still_routes_by_task(self, monkeypatch):
        """Routing keys on task name only; fairness is irrelevant to the decision."""
        monkeypatch.setenv(ENABLED_TASKS_ENV, "bare_task")
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("bare_task")
        # Still dispatched (via Celery), header is None (no fairness).
        assert mock_app.send_task.call_args.args[0] == "bare_task"
        assert mock_app.send_task.call_args.kwargs["headers"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
