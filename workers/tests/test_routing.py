"""Tests for the PG-queue routing gate (``queue_backend.routing``).

Two layers:

1. **select_backend()** resolves the per-task allow-list correctly,
   defaults to ``CELERY`` when unset, and never raises on malformed
   input.

2. **dispatch() is inert under routing** — the ``current_app.send_task``
   call is byte-identical whether the routing table selects ``CELERY``
   or ``PG``. This pins the scaffold invariant: the seam is observable
   (a log line) but changes nothing on the wire until a real PG
   consumer lands.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from queue_backend import QueueBackend, select_backend
from queue_backend.fairness import FairnessKey, WorkloadType

ENABLED_TASKS_ENV = "WORKER_PG_QUEUE_ENABLED_TASKS"


@pytest.fixture(autouse=True)
def _clear_routing_env(monkeypatch):
    """Each test starts from an empty routing table (all-Celery default)."""
    monkeypatch.delenv(ENABLED_TASKS_ENV, raising=False)


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


# --- dispatch() is inert under routing (the scaffold invariant) ---


class TestDispatchByteIdenticalRegardlessOfRouting:
    """``dispatch()`` produces the same send_task call whether routed PG or Celery."""

    def _capture_send_task(self, task_name, fairness):
        from queue_backend import dispatch

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
        from queue_backend import dispatch

        monkeypatch.setenv(ENABLED_TASKS_ENV, "bare_task")
        with patch("queue_backend.dispatch.current_app") as mock_app:
            dispatch("bare_task")
        # Still dispatched (via Celery), header is None (no fairness).
        assert mock_app.send_task.call_args.args[0] == "bare_task"
        assert mock_app.send_task.call_args.kwargs["headers"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
