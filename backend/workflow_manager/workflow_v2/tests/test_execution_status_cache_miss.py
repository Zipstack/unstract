"""UN-3749 — ``_get_execution_status`` must survive an execution-cache miss.

On a miss it rebuilt the cache entry from the ``WorkflowExecution`` row, reading
``execution_model.completed_files`` — a field the model does not have (it has
``successful_files`` and ``failed_files``). Every miss raised
``AttributeError``. In the API sync wait that error lands in the post-dispatch
handler, which returns ``EXECUTING`` at once: the caller saw a running
execution even when the row was already ``COMPLETED``.

A miss now reads the status from the row and writes nothing back. A write-back
could replace a status a worker wrote, or an acknowledgement deleted, after the
read; the worker's next ``save()`` recreates the entry itself.

DB-free: the model row is an unsaved instance and the cache, context and
``time`` are mocked.
"""

from unittest.mock import MagicMock, call, patch

from workflow_manager.execution.dto import ExecutionCache
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_MOD = "workflow_manager.workflow_v2.workflow_helper"


def _row(status: ExecutionStatus) -> WorkflowExecution:
    """A real (unsaved) model instance, so a missing field raises as in prod."""
    return WorkflowExecution(status=status.value)


class TestGetExecutionStatusCacheMiss:
    def test_cache_miss_returns_the_row_status(self):
        with (
            patch(f"{_MOD}.ExecutionCacheUtils") as cache_utils,
            patch(f"{_MOD}.WorkflowExecution") as wf_exec,
        ):
            cache_utils.get_execution.return_value = None
            wf_exec.objects.get.return_value = _row(ExecutionStatus.COMPLETED)

            status = WorkflowHelper._get_execution_status(
                workflow_id="wf-1", execution_id="exec-1"
            )

        assert status == ExecutionStatus.COMPLETED
        wf_exec.objects.get.assert_called_once_with(id="exec-1")

    def test_cache_miss_writes_nothing_back(self):
        # A write-back here races the worker's own cache write: the row read
        # can be older than the status the worker has just cached.
        with (
            patch(f"{_MOD}.ExecutionCacheUtils") as cache_utils,
            patch(f"{_MOD}.WorkflowExecution") as wf_exec,
        ):
            cache_utils.get_execution.return_value = None
            wf_exec.objects.get.return_value = _row(ExecutionStatus.EXECUTING)

            WorkflowHelper._get_execution_status(
                workflow_id="wf-1", execution_id="exec-1"
            )

        # The only ExecutionCacheUtils call is the read: no write-back through it.
        assert cache_utils.method_calls == [
            call.get_execution(workflow_id="wf-1", execution_id="exec-1")
        ]

    def test_cache_hit_does_not_touch_the_row(self):
        cached = ExecutionCache(
            workflow_id="wf-1",
            execution_id="exec-1",
            status=ExecutionStatus.EXECUTING,
        )
        with (
            patch(f"{_MOD}.ExecutionCacheUtils") as cache_utils,
            patch(f"{_MOD}.WorkflowExecution") as wf_exec,
        ):
            cache_utils.get_execution.return_value = cached

            status = WorkflowHelper._get_execution_status(
                workflow_id="wf-1", execution_id="exec-1"
            )

        assert status == ExecutionStatus.EXECUTING
        wf_exec.objects.get.assert_not_called()


class TestSyncWaitSeesCompletionAfterCacheMiss:
    def test_sync_wait_returns_completed_not_executing(self):
        """The user-visible symptom: an API sync wait that hits a cache miss."""
        dispatched_row = MagicMock(status=ExecutionStatus.EXECUTING.value)
        finished_row = _row(ExecutionStatus.COMPLETED)

        with (
            patch(f"{_MOD}.UserContext") as user_ctx,
            patch(f"{_MOD}.StateStore") as state_store,
            patch(f"{_MOD}.time"),
            patch(f"{_MOD}.connections") as conns,
            patch(f"{_MOD}.WorkflowExecution") as wf_exec,
            patch(f"{_MOD}.ExecutionCacheUtils") as cache_utils,
            patch(f"{_MOD}.ResultCacheUtils") as result_cache,
            patch(f"{_MOD}.WorkflowExecutionServiceHelper"),
            patch.object(WorkflowHelper, "_dispatch_orchestrator_task", return_value="1"),
            patch.object(WorkflowHelper, "_record_dispatch_handle"),
            patch.object(WorkflowHelper, "set_result_acknowledge"),
        ):
            user_ctx.get_organization_identifier.return_value = "org1"
            state_store.get.return_value = None
            conns.all.return_value = []
            # Dispatch-time read, then the cache-miss read, then the final fetch.
            wf_exec.objects.get.side_effect = [
                dispatched_row,
                finished_row,
                finished_row,
            ]
            cache_utils.get_execution.return_value = None
            result_cache.get_api_results.return_value = [{"ok": True}]

            response = WorkflowHelper.execute_workflow_async(
                workflow_id="wf-1",
                execution_id="exec-1",
                hash_values_of_files={},
                timeout=4,
            )

        assert response.execution_status == ExecutionStatus.COMPLETED
        assert response.result == [{"ok": True}]
