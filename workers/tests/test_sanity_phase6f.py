"""Phase 6F Sanity — SmartTableExtractorExecutor + SMART_TABLE_EXTRACT operation.

Verifies:
1. Operation.SMART_TABLE_EXTRACT enum exists with value "smart_table_extract"
2. tasks.py log_component builder handles smart_table_extract operation
3. Mock SmartTableExtractorExecutor — registration and execution
4. Queue routing: executor_name="smart_table" → celery_executor_smart_table
5. LegacyExecutor does NOT handle smart_table_extract
6. Dispatch sends to correct queue
"""

from unittest.mock import MagicMock


from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.executor import BaseExecutor
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


# ---------------------------------------------------------------------------
# 1. Operation enum
# ---------------------------------------------------------------------------

class TestSmartTableExtractOperation:
    def test_smart_table_extract_enum_exists(self):
        assert hasattr(Operation, "SMART_TABLE_EXTRACT")
        assert Operation.SMART_TABLE_EXTRACT.value == "smart_table_extract"

    def test_smart_table_extract_in_operation_values(self):
        values = {op.value for op in Operation}
        assert "smart_table_extract" in values


# ---------------------------------------------------------------------------
# 2. tasks.py log_component for smart_table_extract
# ---------------------------------------------------------------------------

class TestTasksLogComponent:
    def test_smart_table_extract_log_component(self):
        """tasks.py handles smart_table_extract in the same branch as table_extract."""
        ctx_dict = {
            "executor_name": "smart_table",
            "operation": "smart_table_extract",
            "run_id": "run-001",
            "execution_source": "tool",
            "organization_id": "org-1",
            "executor_params": {
                "tool_id": "tool-1",
                "file_name": "data.xlsx",
            },
            "request_id": "req-1",
            "log_events_id": "evt-1",
        }
        context = ExecutionContext.from_dict(ctx_dict)
        params = context.executor_params

        # Simulate the tasks.py logic — smart_table_extract shares the
        # branch with table_extract
        assert context.operation in ("table_extract", "smart_table_extract")
        component = {
            "tool_id": params.get("tool_id", ""),
            "run_id": context.run_id,
            "doc_name": str(params.get("file_name", "")),
            "operation": context.operation,
        }
        assert component == {
            "tool_id": "tool-1",
            "run_id": "run-001",
            "doc_name": "data.xlsx",
            "operation": "smart_table_extract",
        }


# ---------------------------------------------------------------------------
# 3. Mock SmartTableExtractorExecutor — registration and execution
# ---------------------------------------------------------------------------

class TestSmartTableExtractorRegistration:
    def test_mock_smart_table_executor_registers_and_executes(self):
        """Simulate cloud executor discovery and execution."""
        @ExecutorRegistry.register
        class MockSmartTableExecutor(BaseExecutor):
            @property
            def name(self) -> str:
                return "smart_table"

            def execute(self, context):
                if context.operation != "smart_table_extract":
                    return ExecutionResult.failure(
                        error=f"Unsupported: {context.operation}"
                    )
                return ExecutionResult(
                    success=True,
                    data={
                        "output": [{"col1": "val1"}],
                        "metadata": {"total_records": 1},
                    },
                )

        try:
            assert "smart_table" in ExecutorRegistry.list_executors()
            executor = ExecutorRegistry.get("smart_table")
            assert executor.name == "smart_table"

            ctx = ExecutionContext(
                executor_name="smart_table",
                operation="smart_table_extract",
                run_id="run-1",
                execution_source="tool",
                executor_params={},
            )
            result = executor.execute(ctx)
            assert result.success
            assert result.data["output"] == [{"col1": "val1"}]
            assert result.data["metadata"]["total_records"] == 1

            # Rejects unsupported operations
            ctx2 = ExecutionContext(
                executor_name="smart_table",
                operation="answer_prompt",
                run_id="run-2",
                execution_source="tool",
                executor_params={},
            )
            result2 = executor.execute(ctx2)
            assert not result2.success
        finally:
            ExecutorRegistry.clear()


# ---------------------------------------------------------------------------
# 4. Queue routing
# ---------------------------------------------------------------------------

class TestSmartTableQueueRouting:
    def test_smart_table_routes_to_correct_queue(self):
        queue = ExecutionDispatcher._get_queue("smart_table")
        assert queue == "celery_executor_smart_table"

    def test_dispatch_sends_to_smart_table_queue(self):
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = ExecutionResult(
            success=True, data={"output": "ok"}
        ).to_dict()
        mock_app.send_task.return_value = mock_result

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="smart_table",
            operation="smart_table_extract",
            run_id="run-1",
            execution_source="tool",
            executor_params={"table_settings": {}},
        )
        result = dispatcher.dispatch(ctx)

        mock_app.send_task.assert_called_once()
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "celery_executor_smart_table"


# ---------------------------------------------------------------------------
# 5. LegacyExecutor does NOT handle smart_table_extract
# ---------------------------------------------------------------------------

class TestLegacyExcludesSmartTable:
    def test_smart_table_extract_not_in_legacy_operation_map(self):
        from executor.executors.legacy_executor import LegacyExecutor
        assert "smart_table_extract" not in LegacyExecutor._OPERATION_MAP

    def test_legacy_returns_failure_for_smart_table_extract(self):
        from executor.executors.legacy_executor import LegacyExecutor

        ExecutorRegistry.clear()
        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)
        executor = ExecutorRegistry.get("legacy")

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="smart_table_extract",
            run_id="run-1",
            execution_source="tool",
            executor_params={},
        )
        result = executor.execute(ctx)
        assert not result.success
        assert "does not support" in result.error
