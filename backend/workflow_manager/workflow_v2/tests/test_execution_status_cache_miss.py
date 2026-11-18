"""UN-3749 — ``_get_execution_status`` must survive an execution-cache miss.

On a miss it rebuilds the cache entry from the ``WorkflowExecution`` row. It
read ``execution_model.completed_files``, a field the model does not have (it
has ``successful_files`` and ``failed_files``), so every miss raised
``AttributeError``. In the API sync wait that error lands in the post-dispatch
handler, which returns ``EXECUTING`` at once: the caller saw a running
execution even when the row was already ``COMPLETED``.

The rebuild writes only fields that are still absent, so a status a worker
wrote between the database read and the cache write is not overwritten.

DB-free: the model row is an unsaved instance and the cache, context and
``time`` are mocked.
"""

from unittest.mock import MagicMock, patch

from workflow_manager.execution.dto import ExecutionCache
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_MOD = "workflow_manager.workflow_v2.workflow_helper"


def _row(status: ExecutionStatus) -> WorkflowExecution:
    """A real (unsaved) model instance, so a missing field raises as in prod."""
    return WorkflowExecution(
        status=status.value, total_files=5, successful_files=3, failed_files=1
    )


class TestGetExecutionStatusCacheMiss:
    def test_cache_miss_rebuilds_entry_from_row(self):
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
        cache_utils.create_execution.assert_not_called()
        cache_utils.create_execution_if_absent.assert_called_once()
        rebuild = cache_utils.create_execution_if_absent
        rebuilt: ExecutionCache = rebuild.call_args.kwargs["execution"]
        assert rebuilt.total_files == 5
        # Completed means processed, success or failure: 3 + 1.
        assert rebuilt.completed_files == 4
        assert rebuilt.failed_files == 1

    def test_cache_miss_tolerates_null_counters(self):
        row = WorkflowExecution(status=ExecutionStatus.PENDING.value)
        row.successful_files = None
        row.failed_files = None
        with (
            patch(f"{_MOD}.ExecutionCacheUtils") as cache_utils,
            patch(f"{_MOD}.WorkflowExecution") as wf_exec,
        ):
            cache_utils.get_execution.return_value = None
            wf_exec.objects.get.return_value = row

            status = WorkflowHelper._get_execution_status(
                workflow_id="wf-1", execution_id="exec-1"
            )

        assert status == ExecutionStatus.PENDING
        rebuilt = cache_utils.create_execution_if_absent.call_args.kwargs["execution"]
        assert rebuilt.completed_files == 0
        assert rebuilt.failed_files == 0

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
        cache_utils.create_execution.assert_not_called()
        cache_utils.create_execution_if_absent.assert_not_called()


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


class TestRebuildNeverOverwritesANewerStatus:
    """The rebuild must not clobber a status written after its database read."""

    def test_create_if_absent_uses_hsetnx_per_field(self):
        from utils.cache_service import CacheService

        with patch("utils.cache_service.redis_cache") as redis_cache:
            pipe = redis_cache.pipeline.return_value
            # status kept (0), the other two fields written (1), then EXPIRE.
            pipe.execute.return_value = [0, 1, 1, True]

            wrote = CacheService.hset_if_absent(
                "execution:wf:ex",
                mapping={"status": "EXECUTING", "total_files": 5, "failed_files": 0},
                expire_time=60,
            )

        redis_cache.pipeline.assert_called_once_with(transaction=True)
        pipe.hset.assert_not_called()
        assert [c.args for c in pipe.hsetnx.call_args_list] == [
            ("execution:wf:ex", "status", "EXECUTING"),
            ("execution:wf:ex", "total_files", 5),
            ("execution:wf:ex", "failed_files", 0),
        ]
        pipe.expire.assert_called_once_with("execution:wf:ex", 60)
        assert wrote is True

    def test_create_if_absent_reports_nothing_written(self):
        from utils.cache_service import CacheService

        with patch("utils.cache_service.redis_cache") as redis_cache:
            redis_cache.pipeline.return_value.execute.return_value = [0, 0, True]
            assert CacheService.hset_if_absent("k", mapping={"a": 1, "b": 2}) is False

    def test_execution_cache_utils_routes_to_if_absent_write(self):
        from workflow_manager.execution.execution_cache_utils import (
            ExecutionCacheUtils,
        )

        entry = ExecutionCache(
            workflow_id="wf-1",
            execution_id="exec-1",
            status=ExecutionStatus.EXECUTING,
            total_files=5,
        )
        with patch(
            "workflow_manager.execution.execution_cache_utils.CacheService"
        ) as cache:
            ExecutionCacheUtils.create_execution_if_absent(entry)

        cache.hset.assert_not_called()
        (key,) = cache.hset_if_absent.call_args.args
        assert key == "execution:wf-1:exec-1"
        assert cache.hset_if_absent.call_args.kwargs["mapping"] == entry.to_json()
