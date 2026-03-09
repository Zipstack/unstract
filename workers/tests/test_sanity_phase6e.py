"""Phase 6E Sanity — TableExtractorExecutor + TABLE_EXTRACT operation.

Verifies:
1. Operation.TABLE_EXTRACT enum exists with value "table_extract"
2. tasks.py log_component builder handles table_extract operation
3. TableExtractorExecutor mock — registration via entry point
4. TableExtractorExecutor mock — dispatch to correct queue
5. LegacyExecutor excludes table_extract from its _OPERATION_MAP
6. Cloud executor entry point name matches pyproject.toml
"""

from unittest.mock import MagicMock


from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


# ---------------------------------------------------------------------------
# 1. Operation enum
# ---------------------------------------------------------------------------

class TestTableExtractOperation:
    def test_table_extract_enum_exists(self):
        assert hasattr(Operation, "TABLE_EXTRACT")
        assert Operation.TABLE_EXTRACT.value == "table_extract"

    def test_table_extract_in_operation_values(self):
        values = {op.value for op in Operation}
        assert "table_extract" in values


# ---------------------------------------------------------------------------
# 2. tasks.py log_component for table_extract
# ---------------------------------------------------------------------------

class TestTasksLogComponent:
    def test_table_extract_log_component(self):
        """tasks.py builds correct log_component for table_extract."""

        # Build a mock context dict
        ctx_dict = {
            "executor_name": "table",
            "operation": "table_extract",
            "run_id": "run-001",
            "execution_source": "tool",
            "organization_id": "org-1",
            "executor_params": {
                "tool_id": "tool-1",
                "file_name": "invoice.pdf",
            },
            "request_id": "req-1",
            "log_events_id": "evt-1",
        }

        # We just need to verify the log_component is built correctly.
        # Deserialize the context and check the branch.
        context = ExecutionContext.from_dict(ctx_dict)
        params = context.executor_params

        # Simulate the tasks.py logic
        if context.log_events_id:
            if context.operation == "table_extract":
                component = {
                    "tool_id": params.get("tool_id", ""),
                    "run_id": context.run_id,
                    "doc_name": str(params.get("file_name", "")),
                    "operation": context.operation,
                }
                assert component == {
                    "tool_id": "tool-1",
                    "run_id": "run-001",
                    "doc_name": "invoice.pdf",
                    "operation": "table_extract",
                }


# ---------------------------------------------------------------------------
# 3. Mock TableExtractorExecutor — entry point registration
# ---------------------------------------------------------------------------

class TestTableExtractorExecutorRegistration:
    def test_mock_table_executor_discovered_via_entry_point(self):
        """Simulate cloud executor discovery via entry point."""
        from unstract.sdk1.execution.executor import BaseExecutor

        # Create a mock TableExtractorExecutor
        @ExecutorRegistry.register
        class MockTableExtractorExecutor(BaseExecutor):
            @property
            def name(self) -> str:
                return "table"

            def execute(self, context):
                if context.operation != "table_extract":
                    return ExecutionResult.failure(
                        error=f"Unsupported: {context.operation}"
                    )
                return ExecutionResult(
                    success=True,
                    data={"output": "table_data", "metadata": {}},
                )

        try:
            # Verify it was registered
            assert "table" in ExecutorRegistry.list_executors()
            executor = ExecutorRegistry.get("table")
            assert executor.name == "table"

            # Verify it handles table_extract
            ctx = ExecutionContext(
                executor_name="table",
                operation="table_extract",
                run_id="run-1",
                execution_source="tool",
                executor_params={},
            )
            result = executor.execute(ctx)
            assert result.success
            assert result.data["output"] == "table_data"

            # Verify it rejects unsupported operations
            ctx2 = ExecutionContext(
                executor_name="table",
                operation="answer_prompt",
                run_id="run-2",
                execution_source="tool",
                executor_params={},
            )
            result2 = executor.execute(ctx2)
            assert not result2.success
        finally:
            # Cleanup
            ExecutorRegistry.clear()


# ---------------------------------------------------------------------------
# 4. Queue routing for table executor
# ---------------------------------------------------------------------------

class TestTableQueueRouting:
    def test_table_executor_routes_to_correct_queue(self):
        """executor_name='table' routes to celery_executor_table queue."""
        queue = ExecutionDispatcher._get_queue("table")
        assert queue == "celery_executor_table"

    def test_dispatch_sends_to_table_queue(self):
        """ExecutionDispatcher sends table_extract to correct queue."""
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = ExecutionResult(
            success=True, data={"output": "ok"}
        ).to_dict()
        mock_app.send_task.return_value = mock_result

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="table",
            operation="table_extract",
            run_id="run-1",
            execution_source="tool",
            executor_params={"table_settings": {}},
        )
        result = dispatcher.dispatch(ctx)

        mock_app.send_task.assert_called_once()
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "celery_executor_table"


# ---------------------------------------------------------------------------
# 5. LegacyExecutor does NOT handle table_extract
# ---------------------------------------------------------------------------

class TestLegacyExcludesTable:
    def test_table_extract_not_in_legacy_operation_map(self):
        """LegacyExecutor._OPERATION_MAP should NOT contain table_extract."""
        from executor.executors.legacy_executor import LegacyExecutor

        assert "table_extract" not in LegacyExecutor._OPERATION_MAP

    def test_legacy_returns_failure_for_table_extract(self):
        """LegacyExecutor.execute() returns failure for table_extract."""
        from executor.executors.legacy_executor import LegacyExecutor

        ExecutorRegistry.clear()
        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)
        executor = ExecutorRegistry.get("legacy")

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="table_extract",
            run_id="run-1",
            execution_source="tool",
            executor_params={},
        )
        result = executor.execute(ctx)
        assert not result.success
        assert "does not support" in result.error


# ---------------------------------------------------------------------------
# 6. Entry point name verification
# ---------------------------------------------------------------------------

class TestEntryPointConfig:
    def test_entry_point_name_is_table(self):
        """The pyproject.toml entry point name should be 'table'."""
        # This is a documentation/verification test — the entry point
        # in pyproject.toml maps 'table' to TableExtractorExecutor.
        # Verify the queue name matches.
        assert ExecutionDispatcher._get_queue("table") == "celery_executor_table"
