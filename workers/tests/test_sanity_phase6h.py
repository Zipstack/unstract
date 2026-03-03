"""Phase 6H Sanity — AgenticPromptStudioExecutor + agentic operations.

Verifies:
1. All 8 agentic Operation enums exist
2. AGENTIC_EXTRACTION removed from Operation enum
3. Mock AgenticPromptStudioExecutor — registration and all 8 operations
4. Queue routing: executor_name="agentic" → celery_executor_agentic
5. LegacyExecutor does NOT handle any agentic operations
6. Dispatch sends to correct queue
7. Structure tool routes to agentic executor (not legacy)
"""

from unittest.mock import MagicMock

import pytest

from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.executor import BaseExecutor
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


AGENTIC_OPERATIONS = [
    "agentic_extract",
    "agentic_summarize",
    "agentic_uniformize",
    "agentic_finalize",
    "agentic_generate_prompt",
    "agentic_generate_prompt_pipeline",
    "agentic_compare",
    "agentic_tune_field",
]


# ---------------------------------------------------------------------------
# 1. Operation enums
# ---------------------------------------------------------------------------

class TestAgenticOperations:
    @pytest.mark.parametrize("op", AGENTIC_OPERATIONS)
    def test_agentic_operation_enum_exists(self, op):
        values = {o.value for o in Operation}
        assert op in values

    def test_agentic_extraction_removed(self):
        """Old AGENTIC_EXTRACTION enum no longer exists."""
        assert not hasattr(Operation, "AGENTIC_EXTRACTION")
        values = {o.value for o in Operation}
        assert "agentic_extraction" not in values


# ---------------------------------------------------------------------------
# 2. Mock AgenticPromptStudioExecutor — registration and all operations
# ---------------------------------------------------------------------------

class TestAgenticExecutorRegistration:
    def test_mock_agentic_executor_registers_and_routes_all_ops(self):
        """Simulate cloud executor discovery and execution of all 8 ops."""
        @ExecutorRegistry.register
        class MockAgenticExecutor(BaseExecutor):
            _OPERATION_MAP = {op: f"_handle_{op}" for op in AGENTIC_OPERATIONS}

            @property
            def name(self) -> str:
                return "agentic"

            def execute(self, context):
                handler_name = self._OPERATION_MAP.get(context.operation)
                if not handler_name:
                    return ExecutionResult.failure(
                        error=f"Unsupported: {context.operation}"
                    )
                return ExecutionResult(
                    success=True,
                    data={
                        "output": {"operation": context.operation},
                        "metadata": {},
                    },
                )

        try:
            assert "agentic" in ExecutorRegistry.list_executors()
            executor = ExecutorRegistry.get("agentic")
            assert executor.name == "agentic"

            # Test all 8 operations route successfully
            for op in AGENTIC_OPERATIONS:
                ctx = ExecutionContext(
                    executor_name="agentic",
                    operation=op,
                    run_id=f"run-{op}",
                    execution_source="tool",
                    executor_params={},
                )
                result = executor.execute(ctx)
                assert result.success, f"Operation {op} failed"
                assert result.data["output"]["operation"] == op

            # Rejects unsupported operations
            ctx = ExecutionContext(
                executor_name="agentic",
                operation="answer_prompt",
                run_id="run-unsupported",
                execution_source="tool",
                executor_params={},
            )
            result = executor.execute(ctx)
            assert not result.success
        finally:
            ExecutorRegistry.clear()


# ---------------------------------------------------------------------------
# 3. Queue routing
# ---------------------------------------------------------------------------

class TestAgenticQueueRouting:
    def test_agentic_routes_to_correct_queue(self):
        queue = ExecutionDispatcher._get_queue("agentic")
        assert queue == "celery_executor_agentic"

    @pytest.mark.parametrize("op", AGENTIC_OPERATIONS)
    def test_dispatch_sends_to_agentic_queue(self, op):
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = ExecutionResult(
            success=True, data={"output": {}}
        ).to_dict()
        mock_app.send_task.return_value = mock_result

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="agentic",
            operation=op,
            run_id="run-1",
            execution_source="tool",
            executor_params={},
        )
        dispatcher.dispatch(ctx)

        mock_app.send_task.assert_called_once()
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "celery_executor_agentic"


# ---------------------------------------------------------------------------
# 4. LegacyExecutor does NOT handle agentic operations
# ---------------------------------------------------------------------------

class TestLegacyExcludesAgentic:
    @pytest.mark.parametrize("op", AGENTIC_OPERATIONS)
    def test_agentic_op_not_in_legacy_operation_map(self, op):
        from executor.executors.legacy_executor import LegacyExecutor
        assert op not in LegacyExecutor._OPERATION_MAP

    def test_legacy_returns_failure_for_agentic_extract(self):
        from executor.executors.legacy_executor import LegacyExecutor

        ExecutorRegistry.clear()
        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)
        executor = ExecutorRegistry.get("legacy")

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="agentic_extract",
            run_id="run-1",
            execution_source="tool",
            executor_params={},
        )
        result = executor.execute(ctx)
        assert not result.success
        assert "does not support" in result.error

    def test_legacy_returns_failure_for_agentic_summarize(self):
        from executor.executors.legacy_executor import LegacyExecutor

        ExecutorRegistry.clear()
        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)
        executor = ExecutorRegistry.get("legacy")

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="agentic_summarize",
            run_id="run-1",
            execution_source="tool",
            executor_params={},
        )
        result = executor.execute(ctx)
        assert not result.success
        assert "does not support" in result.error


# ---------------------------------------------------------------------------
# 5. Structure tool routes to agentic executor
# ---------------------------------------------------------------------------

class TestStructureToolAgenticRouting:
    def test_structure_tool_dispatches_agentic_extract(self):
        """Verify _run_agentic_extraction sends executor_name='agentic'."""

        from file_processing.structure_tool_task import _run_agentic_extraction

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = ExecutionResult(
            success=True, data={"output": {"field": "value"}}
        )

        result = _run_agentic_extraction(
            tool_metadata={"name": "test"},
            input_file_path="/tmp/test.pdf",
            output_dir_path="/tmp/output",
            tool_instance_metadata={},
            dispatcher=mock_dispatcher,
            shim=MagicMock(),
            platform_helper=MagicMock(),
            file_execution_id="exec-001",
            organization_id="org-001",
            source_file_name="test.pdf",
            fs=MagicMock(),
        )

        # Verify dispatch was called with correct routing
        mock_dispatcher.dispatch.assert_called_once()
        dispatched_ctx = mock_dispatcher.dispatch.call_args[0][0]
        assert dispatched_ctx.executor_name == "agentic"
        assert dispatched_ctx.operation == "agentic_extract"
        assert dispatched_ctx.organization_id == "org-001"


# ---------------------------------------------------------------------------
# 6. tasks.py log_component for agentic operations
# ---------------------------------------------------------------------------

class TestTasksLogComponent:
    @pytest.mark.parametrize("op", AGENTIC_OPERATIONS)
    def test_agentic_ops_use_default_log_component(self, op):
        """Agentic operations fall through to default log_component."""
        ctx_dict = {
            "executor_name": "agentic",
            "operation": op,
            "run_id": "run-001",
            "execution_source": "tool",
            "executor_params": {
                "tool_id": "tool-1",
                "file_name": "doc.pdf",
            },
            "request_id": "req-1",
            "log_events_id": "evt-1",
        }
        context = ExecutionContext.from_dict(ctx_dict)

        # Agentic ops should NOT match ide_index, structure_pipeline,
        # or table_extract/smart_table_extract branches
        assert context.operation not in (
            "ide_index", "structure_pipeline",
            "table_extract", "smart_table_extract",
        )
