"""Tests for WorkflowHelper._dispatch_orchestrator_task — the PG-vs-Celery
orchestrator dispatch fork (9e 2d).

DB-free: pg_enqueue_task and celery_app are mocked, so these pin the routing
decision (PG enqueue vs Celery send), the bare-msg_id task-id contract, the
WorkloadType value, and the two org sentinels.
"""

from unittest.mock import MagicMock, patch

from utils.constants import CeleryQueue
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_PG = "workflow_manager.workflow_v2.workflow_helper.pg_enqueue_task"
_CELERY = "workflow_manager.workflow_v2.workflow_helper.celery_app"


class TestDispatchOrchestratorTask:
    def test_pg_transport_enqueues_to_pg_not_celery(self):
        with patch(_PG, return_value=4242) as pg, patch(_CELERY) as celery:
            task_id = WorkflowHelper._dispatch_orchestrator_task(
                transport="pg_queue",
                queue=CeleryQueue.CELERY_API_DEPLOYMENTS,
                args=["a"],
                kwargs={"transport": "pg_queue"},
                org_schema="org1",
            )
        # bare msg_id, no "pg:" prefix — matches the worker PgDispatchHandle.id
        assert task_id == "4242"
        celery.send_task.assert_not_called()
        kw = pg.call_args.kwargs
        assert kw["task_name"] == "async_execute_bin"
        assert kw["queue"] == CeleryQueue.CELERY_API_DEPLOYMENTS
        assert kw["org_id"] == "org1"
        assert kw["fairness"]["workload_type"] == "api"

    def test_pg_general_queue_uses_non_api_workload(self):
        with patch(_PG, return_value=7) as pg, patch(_CELERY):
            WorkflowHelper._dispatch_orchestrator_task(
                transport="pg_queue", queue=None, args=[], kwargs={}, org_schema="org1"
            )
        assert pg.call_args.kwargs["fairness"]["workload_type"] == "non_api"

    def test_empty_org_uses_two_sentinels(self):
        """Row org_id column is NOT NULL → ""; fairness org_id is str|None → None."""
        with patch(_PG, return_value=1) as pg, patch(_CELERY):
            WorkflowHelper._dispatch_orchestrator_task(
                transport="pg_queue", queue=None, args=[], kwargs={}, org_schema=""
            )
        kw = pg.call_args.kwargs
        assert kw["org_id"] == ""
        assert kw["fairness"]["org_id"] is None

    def test_celery_transport_uses_send_task_not_pg(self):
        with patch(_PG) as pg, patch(_CELERY) as celery:
            celery.send_task.return_value = MagicMock(id="celery-task-1")
            task_id = WorkflowHelper._dispatch_orchestrator_task(
                transport="celery", queue=None, args=[], kwargs={}, org_schema="org1"
            )
        assert task_id == "celery-task-1"
        pg.assert_not_called()
        celery.send_task.assert_called_once()
