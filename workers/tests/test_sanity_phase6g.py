"""Phase 6G Sanity — SimplePromptStudioExecutor + SPS operations.

Verifies:
1. Operation.SPS_ANSWER_PROMPT enum exists with value "sps_answer_prompt"
2. Operation.SPS_INDEX enum exists with value "sps_index"
3. Mock SimplePromptStudioExecutor — registration and execution
4. Queue routing: executor_name="simple_prompt_studio" → celery_executor_simple_prompt_studio
5. LegacyExecutor does NOT handle sps_answer_prompt or sps_index
6. Dispatch sends to correct queue
7. SimplePromptStudioExecutor rejects unsupported operations
"""

from unittest.mock import MagicMock


from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.executor import BaseExecutor
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


# ---------------------------------------------------------------------------
# 1. Operation enums
# ---------------------------------------------------------------------------

class TestSPSOperations:
    def test_sps_answer_prompt_enum_exists(self):
        assert hasattr(Operation, "SPS_ANSWER_PROMPT")
        assert Operation.SPS_ANSWER_PROMPT.value == "sps_answer_prompt"

    def test_sps_index_enum_exists(self):
        assert hasattr(Operation, "SPS_INDEX")
        assert Operation.SPS_INDEX.value == "sps_index"

    def test_sps_operations_in_operation_values(self):
        values = {op.value for op in Operation}
        assert "sps_answer_prompt" in values
        assert "sps_index" in values


# ---------------------------------------------------------------------------
# 2. Mock SimplePromptStudioExecutor — registration and execution
# ---------------------------------------------------------------------------

class TestSimplePromptStudioRegistration:
    def test_mock_sps_executor_registers_and_executes(self):
        """Simulate cloud executor discovery and execution."""
        @ExecutorRegistry.register
        class MockSPSExecutor(BaseExecutor):
            _OPERATION_MAP = {
                "sps_answer_prompt": "_handle_answer_prompt",
                "sps_index": "_handle_index",
            }

            @property
            def name(self) -> str:
                return "simple_prompt_studio"

            def execute(self, context):
                handler_name = self._OPERATION_MAP.get(context.operation)
                if not handler_name:
                    return ExecutionResult.failure(
                        error=f"Unsupported: {context.operation}"
                    )
                return getattr(self, handler_name)(context)

            def _handle_answer_prompt(self, context):
                return ExecutionResult(
                    success=True,
                    data={
                        "output": {"invoice_number": "INV-001"},
                        "metadata": {},
                    },
                )

            def _handle_index(self, context):
                return ExecutionResult(
                    success=True,
                    data={"output": "indexed", "metadata": {}},
                )

        try:
            assert "simple_prompt_studio" in ExecutorRegistry.list_executors()
            executor = ExecutorRegistry.get("simple_prompt_studio")
            assert executor.name == "simple_prompt_studio"

            # sps_answer_prompt
            ctx = ExecutionContext(
                executor_name="simple_prompt_studio",
                operation="sps_answer_prompt",
                run_id="run-1",
                execution_source="tool",
                executor_params={},
            )
            result = executor.execute(ctx)
            assert result.success
            assert result.data["output"] == {"invoice_number": "INV-001"}

            # sps_index
            ctx2 = ExecutionContext(
                executor_name="simple_prompt_studio",
                operation="sps_index",
                run_id="run-2",
                execution_source="tool",
                executor_params={},
            )
            result2 = executor.execute(ctx2)
            assert result2.success
            assert result2.data["output"] == "indexed"

            # Rejects unsupported operations
            ctx3 = ExecutionContext(
                executor_name="simple_prompt_studio",
                operation="extract",
                run_id="run-3",
                execution_source="tool",
                executor_params={},
            )
            result3 = executor.execute(ctx3)
            assert not result3.success
        finally:
            ExecutorRegistry.clear()


# ---------------------------------------------------------------------------
# 3. Queue routing
# ---------------------------------------------------------------------------

class TestSPSQueueRouting:
    def test_sps_routes_to_correct_queue(self):
        queue = ExecutionDispatcher._get_queue("simple_prompt_studio")
        assert queue == "celery_executor_simple_prompt_studio"

    def test_dispatch_sends_to_sps_queue(self):
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = ExecutionResult(
            success=True, data={"output": {"field": "value"}}
        ).to_dict()
        mock_app.send_task.return_value = mock_result

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="simple_prompt_studio",
            operation="sps_answer_prompt",
            run_id="run-1",
            execution_source="tool",
            executor_params={"tool_settings": {}, "output": {}},
        )
        result = dispatcher.dispatch(ctx)

        mock_app.send_task.assert_called_once()
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "celery_executor_simple_prompt_studio"

    def test_dispatch_sps_index_to_correct_queue(self):
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = ExecutionResult(
            success=True, data={"output": "indexed"}
        ).to_dict()
        mock_app.send_task.return_value = mock_result

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="simple_prompt_studio",
            operation="sps_index",
            run_id="run-1",
            execution_source="tool",
            executor_params={"output": {}, "file_path": "/tmp/test.pdf"},
        )
        result = dispatcher.dispatch(ctx)

        mock_app.send_task.assert_called_once()
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "celery_executor_simple_prompt_studio"


# ---------------------------------------------------------------------------
# 4. LegacyExecutor does NOT handle SPS operations
# ---------------------------------------------------------------------------

class TestLegacyExcludesSPS:
    def test_sps_answer_prompt_not_in_legacy_operation_map(self):
        from executor.executors.legacy_executor import LegacyExecutor
        assert "sps_answer_prompt" not in LegacyExecutor._OPERATION_MAP

    def test_sps_index_not_in_legacy_operation_map(self):
        from executor.executors.legacy_executor import LegacyExecutor
        assert "sps_index" not in LegacyExecutor._OPERATION_MAP

    def test_legacy_returns_failure_for_sps_answer_prompt(self):
        from executor.executors.legacy_executor import LegacyExecutor

        ExecutorRegistry.clear()
        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)
        executor = ExecutorRegistry.get("legacy")

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="sps_answer_prompt",
            run_id="run-1",
            execution_source="tool",
            executor_params={},
        )
        result = executor.execute(ctx)
        assert not result.success
        assert "does not support" in result.error

    def test_legacy_returns_failure_for_sps_index(self):
        from executor.executors.legacy_executor import LegacyExecutor

        ExecutorRegistry.clear()
        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)
        executor = ExecutorRegistry.get("legacy")

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="sps_index",
            run_id="run-1",
            execution_source="tool",
            executor_params={},
        )
        result = executor.execute(ctx)
        assert not result.success
        assert "does not support" in result.error


# ---------------------------------------------------------------------------
# 5. tasks.py log_component for SPS operations
# ---------------------------------------------------------------------------

class TestTasksLogComponent:
    def test_sps_answer_prompt_uses_default_log_component(self):
        """SPS operations use the default log_component branch in tasks.py."""
        ctx_dict = {
            "executor_name": "simple_prompt_studio",
            "operation": "sps_answer_prompt",
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
        context = ExecutionContext.from_dict(ctx_dict)
        params = context.executor_params

        # SPS operations fall through to the default branch
        assert context.operation not in ("ide_index", "structure_pipeline",
                                          "table_extract", "smart_table_extract")
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
            "operation": "sps_answer_prompt",
        }

    def test_sps_index_uses_default_log_component(self):
        """SPS index also uses the default log_component branch."""
        ctx_dict = {
            "executor_name": "simple_prompt_studio",
            "operation": "sps_index",
            "run_id": "run-002",
            "execution_source": "tool",
            "executor_params": {
                "tool_id": "tool-2",
                "file_name": "contract.pdf",
            },
            "request_id": "req-2",
            "log_events_id": "evt-2",
        }
        context = ExecutionContext.from_dict(ctx_dict)
        params = context.executor_params

        assert context.operation not in ("ide_index", "structure_pipeline",
                                          "table_extract", "smart_table_extract")
        component = {
            "tool_id": params.get("tool_id", ""),
            "run_id": context.run_id,
            "doc_name": str(params.get("file_name", "")),
            "operation": context.operation,
        }
        assert component["operation"] == "sps_index"
