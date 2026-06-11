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

import psycopg2
import pytest
from queue_backend import dispatch
from queue_backend.fairness import FairnessKey, WorkloadType
from queue_backend.pg_queue import PgQueueClient, to_payload
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.routing import _ENABLED_TASKS_ENV_VAR as ENABLED_TASKS_ENV

# ``queue_backend.dispatch`` the attribute is the function (shadows the
# submodule) — import the module explicitly to reach its globals.
dispatch_mod = importlib.import_module("queue_backend.dispatch")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv(ENABLED_TASKS_ENV, raising=False)
    dispatch_mod._pg_routing_logged.clear()
    dispatch_mod._pg_client = None


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


def _test_conn():
    os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
    return create_pg_connection(env_prefix="TEST_DB_")


@pytest.fixture
def pg_client():
    try:
        conn = _test_conn()
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pg_queue_message')")
        if cur.fetchone()[0] is None:
            conn.close()
            pytest.skip("pg_queue migration not applied (run backend migrate)")
    yield PgQueueClient(conn=conn)
    conn.rollback()
    conn.close()


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
