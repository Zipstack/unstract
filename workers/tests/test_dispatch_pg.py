"""dispatch() PG enqueue (9b) + the ``TaskPayload`` wire shape.

The mocked routing/handle behaviour lives in ``test_routing.py``; this
file covers the message serialisation contract and an end-to-end
integration check (a PG-selected ``dispatch()`` lands a decodable row in
``pg_queue_message``). The integration test skips if Postgres is
unreachable or unmigrated.
"""

from __future__ import annotations

import importlib
import json
import os
from unittest.mock import patch

import pytest
from queue_backend import dispatch
from queue_backend.fairness import FairnessKey, WorkloadType
from queue_backend.pg_queue import to_payload
from queue_backend.routing import _ENABLED_TASKS_ENV_VAR as ENABLED_TASKS_ENV
from queue_backend.routing import QueueBackend

# ``queue_backend.dispatch`` the attribute is the function (shadows the
# submodule) — import the module explicitly to reach its globals.
dispatch_mod = importlib.import_module("queue_backend.dispatch")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv(ENABLED_TASKS_ENV, raising=False)
    dispatch_mod._pg_routing_logged.clear()
    dispatch_mod._pg_local.client = None


# --- to_payload wire shape ---


class TestToPayload:
    def test_minimal(self):
        assert to_payload("t") == {
            "task_name": "t",
            "args": [],
            "kwargs": {},
            "queue": None,
            "fairness": None,
        }

    def test_full(self):
        fairness = FairnessKey(
            org_id="o", workload_type=WorkloadType.API, pipeline_priority=7
        )
        payload = to_payload(
            "t", args=("a", 1), kwargs={"k": "v"}, queue="q", fairness=fairness
        )
        assert payload["args"] == ["a", 1]  # tuple → list
        assert payload["queue"] == "q"
        assert payload["fairness"] == {
            "org_id": "o",
            "workload_type": "api",
            "pipeline_priority": 7,
        }

    def test_json_serialisable(self):
        fairness = FairnessKey(org_id="o", workload_type=WorkloadType.NON_API)
        # Must round-trip through JSON (it's stored in a JSONB column).
        json.dumps(to_payload("t", args=[1], kwargs={"a": "b"}, fairness=fairness))


# --- Integration: dispatch() lands a decodable row in pg_queue_message ---
# Uses the shared ``pg_client`` fixture from conftest.py.


class TestDispatchEnqueueIntegration:
    def test_dispatch_lands_decodable_row(self, monkeypatch, pg_client):
        queue_name = f"test_dispatch_{os.getpid()}"
        monkeypatch.setenv(ENABLED_TASKS_ENV, "leaf_task")
        monkeypatch.setattr(dispatch_mod, "_get_pg_client", lambda: pg_client)
        fairness = FairnessKey(org_id="org-x", workload_type=WorkloadType.API)
        try:
            handle = dispatch(
                "leaf_task",
                args=[1, 2],
                kwargs={"k": "v"},
                queue=queue_name,
                fairness=fairness,
            )
            msgs = pg_client.read(queue_name, vt_seconds=30, qty=10)
            assert len(msgs) == 1
            assert str(msgs[0].msg_id) == handle.id
            message = msgs[0].message
            assert message["task_name"] == "leaf_task"
            assert message["args"] == [1, 2]
            assert message["kwargs"] == {"k": "v"}
            assert message["queue"] == queue_name
            assert message["fairness"]["org_id"] == "org-x"
        finally:
            with pg_client.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM pg_queue_message WHERE queue_name = %s", (queue_name,)
                )
            pg_client.conn.commit()

    def test_celery_dispatch_unaffected(self):
        # No opt-in → Celery path; never touches the PG client.
        with (
            patch("queue_backend.dispatch.current_app") as mock_app,
            patch("queue_backend.dispatch._get_pg_client") as mock_get,
        ):
            dispatch("some_task", args=["x"], queue="general")
        mock_app.send_task.assert_called_once()
        mock_get.assert_not_called()


class TestDispatchBackendOverride:
    """The per-call ``backend=`` override (9e PR 2a inert foundation).

    When set it wins over the ``WORKER_PG_QUEUE_ENABLED_TASKS`` allow-list, so
    the execution-level PG pipeline can route a whole execution's headers /
    callback onto PG without opting their task *names* in. ``None`` (default)
    preserves the allow-list decision exactly — every call site today.
    """

    def test_override_pg_forces_pg_without_allow_list(self, monkeypatch):
        # Task name NOT in the (empty) allow-list → select_backend says Celery;
        # the explicit override must still route it to PG.
        captured: dict = {}

        class _Client:
            def send(self, queue_name, payload, **kwargs):
                captured.update(queue=queue_name, payload=payload, **kwargs)
                return 11

        monkeypatch.setattr(dispatch_mod, "_get_pg_client", lambda: _Client())
        with patch("queue_backend.dispatch.current_app") as mock_app:
            handle = dispatch(
                "pipeline_header", queue="general", backend=QueueBackend.PG
            )
        mock_app.send_task.assert_not_called()
        assert handle.id == "11"
        assert captured["payload"]["task_name"] == "pipeline_header"

    def test_override_celery_forces_celery_despite_allow_list(self, monkeypatch):
        # Task name IS opted into PG, but the override pins it back to Celery.
        monkeypatch.setenv(ENABLED_TASKS_ENV, "pipeline_header")
        with (
            patch("queue_backend.dispatch.current_app") as mock_app,
            patch("queue_backend.dispatch._get_pg_client") as mock_get,
        ):
            dispatch("pipeline_header", queue="general", backend=QueueBackend.CELERY)
        mock_app.send_task.assert_called_once()
        mock_get.assert_not_called()

    def test_default_none_preserves_allow_list_decision(self, monkeypatch):
        # No override → allow-list decides. Opted-in name → PG.
        captured: dict = {}

        class _Client:
            def send(self, queue_name, payload, **kwargs):
                captured.update(queue=queue_name)
                return 5

        monkeypatch.setenv(ENABLED_TASKS_ENV, "leaf_task")
        monkeypatch.setattr(dispatch_mod, "_get_pg_client", lambda: _Client())
        with patch("queue_backend.dispatch.current_app") as mock_app:
            handle = dispatch("leaf_task", queue="general")
        mock_app.send_task.assert_not_called()
        assert handle.id == "5"

    def test_override_path_carries_fairness_to_row(self, monkeypatch):
        # The override's whole purpose is to route an *execution's* dispatches —
        # exactly the ones that carry a FairnessKey. The org/priority plumbing
        # must work identically on the override path (not just the allow-list
        # path), so a regression dropping fairness here would otherwise pass.
        captured: dict = {}

        class _Client:
            def send(self, queue_name, payload, **kwargs):
                captured.update(queue=queue_name, **kwargs)
                return 13

        monkeypatch.setattr(dispatch_mod, "_get_pg_client", lambda: _Client())
        fairness = FairnessKey(
            org_id="o", workload_type=WorkloadType.API, pipeline_priority=8
        )
        with patch("queue_backend.dispatch.current_app"):
            dispatch(
                "pipeline_header",
                queue="general",
                fairness=fairness,
                backend=QueueBackend.PG,
            )
        assert captured["priority"] == 8
        assert captured["org_id"] == "o"


class TestDispatchPriorityWiring:
    """dispatch() carries fairness.pipeline_priority onto the PG row (mocked)."""

    @staticmethod
    def _capture_send(monkeypatch):
        captured: dict = {}

        class _Client:
            def send(self, queue_name, payload, **kwargs):
                captured.update(queue=queue_name, **kwargs)
                return 7

        monkeypatch.setenv(ENABLED_TASKS_ENV, "leaf_task")
        monkeypatch.setattr(dispatch_mod, "_get_pg_client", lambda: _Client())
        return captured

    def test_priority_from_fairness(self, monkeypatch):
        captured = self._capture_send(monkeypatch)
        fairness = FairnessKey(
            org_id="o", workload_type=WorkloadType.API, pipeline_priority=8
        )
        dispatch("leaf_task", fairness=fairness)
        assert captured["priority"] == 8
        assert captured["org_id"] == "o"

    def test_no_fairness_uses_neutral_defaults(self, monkeypatch):
        # Bare dispatch → org_id None (client coerces to "") + DEFAULT_PRIORITY.
        from queue_backend.fairness import DEFAULT_PRIORITY

        captured = self._capture_send(monkeypatch)
        dispatch("leaf_task")
        assert captured["priority"] == DEFAULT_PRIORITY
        assert captured["org_id"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
