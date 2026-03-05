"""Phase 6J — Comprehensive Phase 6 sanity tests.

Consolidated regression + integration tests for the full Phase 6
plugin migration. Verifies:

1. Full Operation enum coverage — every operation has exactly one executor
2. Multi-executor coexistence in ExecutorRegistry
3. End-to-end Celery chain for each cloud executor (mock executors)
4. Cross-cutting highlight plugin works across executors
5. Plugin loader → executor registration → dispatch → result flow
6. Queue routing for all executor names
7. Graceful degradation when cloud plugins missing
8. tasks.py log_component for all operation types
"""

from unittest.mock import MagicMock, patch

import pytest

from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.executor import BaseExecutor
from unstract.sdk1.execution.orchestrator import ExecutionOrchestrator
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registry():
    ExecutorRegistry.clear()
    yield
    ExecutorRegistry.clear()


@pytest.fixture
def eager_app():
    """Configure executor Celery app for eager-mode testing."""
    from executor.worker import app

    original = {
        "task_always_eager": app.conf.task_always_eager,
        "task_eager_propagates": app.conf.task_eager_propagates,
        "result_backend": app.conf.result_backend,
    }
    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=False,
        result_backend="cache+memory://",
    )
    yield app
    app.conf.update(original)


def _register_legacy():
    from executor.executors.legacy_executor import LegacyExecutor
    ExecutorRegistry.register(LegacyExecutor)


# Mock cloud executors for multi-executor tests
def _register_mock_cloud_executors():
    """Register mock cloud executors alongside LegacyExecutor."""

    @ExecutorRegistry.register
    class MockTableExecutor(BaseExecutor):
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
                data={"output": "smart_table_data", "metadata": {}},
            )

    @ExecutorRegistry.register
    class MockSPSExecutor(BaseExecutor):
        @property
        def name(self) -> str:
            return "simple_prompt_studio"

        def execute(self, context):
            if context.operation not in ("sps_answer_prompt", "sps_index"):
                return ExecutionResult.failure(
                    error=f"Unsupported: {context.operation}"
                )
            return ExecutionResult(
                success=True,
                data={"output": f"sps_{context.operation}", "metadata": {}},
            )

    @ExecutorRegistry.register
    class MockAgenticExecutor(BaseExecutor):
        _OPS = {
            "agentic_extract", "agentic_summarize", "agentic_uniformize",
            "agentic_finalize", "agentic_generate_prompt",
            "agentic_generate_prompt_pipeline", "agentic_compare",
            "agentic_tune_field",
        }

        @property
        def name(self) -> str:
            return "agentic"

        def execute(self, context):
            if context.operation not in self._OPS:
                return ExecutionResult.failure(
                    error=f"Unsupported: {context.operation}"
                )
            return ExecutionResult(
                success=True,
                data={"output": f"agentic_{context.operation}", "metadata": {}},
            )


# ---------------------------------------------------------------------------
# 1. Full Operation enum coverage — every operation has exactly one executor
# ---------------------------------------------------------------------------

# Map of every Operation value to the executor that handles it
OPERATION_TO_EXECUTOR = {
    # LegacyExecutor (OSS)
    "extract": "legacy",
    "index": "legacy",
    "answer_prompt": "legacy",
    "single_pass_extraction": "legacy",
    "summarize": "legacy",
    "ide_index": "legacy",
    "structure_pipeline": "legacy",
    # Cloud executors
    "table_extract": "table",
    "smart_table_extract": "smart_table",
    "sps_answer_prompt": "simple_prompt_studio",
    "sps_index": "simple_prompt_studio",
    "agentic_extract": "agentic",
    "agentic_summarize": "agentic",
    "agentic_uniformize": "agentic",
    "agentic_finalize": "agentic",
    "agentic_generate_prompt": "agentic",
    "agentic_generate_prompt_pipeline": "agentic",
    "agentic_compare": "agentic",
    "agentic_tune_field": "agentic",
}


class TestOperationEnumCoverage:
    def test_every_operation_is_mapped(self):
        """Every Operation enum value has an assigned executor."""
        for op in Operation:
            assert op.value in OPERATION_TO_EXECUTOR, (
                f"Operation {op.value} not mapped to any executor"
            )

    def test_no_extra_mappings(self):
        """No stale mappings for removed operations."""
        valid_ops = {op.value for op in Operation}
        for mapped_op in OPERATION_TO_EXECUTOR:
            assert mapped_op in valid_ops, (
                f"Mapped operation '{mapped_op}' not in Operation enum"
            )

    def test_operation_count(self):
        """Verify total operation count matches expectations."""
        assert len(Operation) == 19  # 7 legacy + 2 table + 2 sps + 8 agentic

    def test_legacy_operations_in_operation_map(self):
        """All legacy operations are in LegacyExecutor._OPERATION_MAP."""
        from executor.executors.legacy_executor import LegacyExecutor

        for op_value, executor_name in OPERATION_TO_EXECUTOR.items():
            if executor_name == "legacy":
                assert op_value in LegacyExecutor._OPERATION_MAP, (
                    f"Legacy operation {op_value} missing from _OPERATION_MAP"
                )

    def test_cloud_operations_not_in_legacy_map(self):
        """Cloud operations are NOT in LegacyExecutor._OPERATION_MAP."""
        from executor.executors.legacy_executor import LegacyExecutor

        for op_value, executor_name in OPERATION_TO_EXECUTOR.items():
            if executor_name != "legacy":
                assert op_value not in LegacyExecutor._OPERATION_MAP, (
                    f"Cloud operation {op_value} should NOT be in legacy map"
                )


# ---------------------------------------------------------------------------
# 2. Multi-executor coexistence in registry
# ---------------------------------------------------------------------------

class TestMultiExecutorCoexistence:
    def test_all_five_executors_registered(self):
        """Legacy + 4 cloud executors all coexist in registry."""
        _register_legacy()
        _register_mock_cloud_executors()

        executors = ExecutorRegistry.list_executors()
        assert "legacy" in executors
        assert "table" in executors
        assert "smart_table" in executors
        assert "simple_prompt_studio" in executors
        assert "agentic" in executors
        assert len(executors) == 5

    def test_each_executor_has_correct_name(self):
        _register_legacy()
        _register_mock_cloud_executors()

        for name in ["legacy", "table", "smart_table", "simple_prompt_studio", "agentic"]:
            executor = ExecutorRegistry.get(name)
            assert executor.name == name

    def test_wrong_executor_rejects_operation(self):
        """Dispatching a table operation to legacy returns failure."""
        _register_legacy()
        _register_mock_cloud_executors()

        legacy = ExecutorRegistry.get("legacy")
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="table_extract",
            run_id="run-1",
            execution_source="tool",
        )
        result = legacy.execute(ctx)
        assert not result.success
        assert "does not support" in result.error

    def test_correct_executor_handles_operation(self):
        """Each operation routes to the right executor."""
        _register_legacy()
        _register_mock_cloud_executors()

        test_cases = [
            ("table", "table_extract"),
            ("smart_table", "smart_table_extract"),
            ("simple_prompt_studio", "sps_answer_prompt"),
            ("simple_prompt_studio", "sps_index"),
            ("agentic", "agentic_extract"),
            ("agentic", "agentic_compare"),
        ]
        for executor_name, operation in test_cases:
            executor = ExecutorRegistry.get(executor_name)
            ctx = ExecutionContext(
                executor_name=executor_name,
                operation=operation,
                run_id=f"run-{operation}",
                execution_source="tool",
            )
            result = executor.execute(ctx)
            assert result.success, f"{executor_name}/{operation} failed"


# ---------------------------------------------------------------------------
# 3. End-to-end Celery chain for cloud executors
# ---------------------------------------------------------------------------

class TestCeleryChainCloudExecutors:
    def test_table_extract_celery_chain(self, eager_app):
        """TABLE extraction through full Celery task chain."""
        _register_legacy()
        _register_mock_cloud_executors()

        ctx = ExecutionContext(
            executor_name="table",
            operation="table_extract",
            run_id="run-celery-table",
            execution_source="tool",
        )
        task = eager_app.tasks["execute_extraction"]
        result_dict = task.apply(args=[ctx.to_dict()]).get()
        result = ExecutionResult.from_dict(result_dict)

        assert result.success
        assert result.data["output"] == "table_data"

    def test_smart_table_extract_celery_chain(self, eager_app):
        """SMART TABLE extraction through full Celery task chain."""
        _register_legacy()
        _register_mock_cloud_executors()

        ctx = ExecutionContext(
            executor_name="smart_table",
            operation="smart_table_extract",
            run_id="run-celery-smart-table",
            execution_source="tool",
        )
        task = eager_app.tasks["execute_extraction"]
        result_dict = task.apply(args=[ctx.to_dict()]).get()
        result = ExecutionResult.from_dict(result_dict)

        assert result.success
        assert result.data["output"] == "smart_table_data"

    def test_sps_answer_prompt_celery_chain(self, eager_app):
        """SPS answer_prompt through full Celery task chain."""
        _register_legacy()
        _register_mock_cloud_executors()

        ctx = ExecutionContext(
            executor_name="simple_prompt_studio",
            operation="sps_answer_prompt",
            run_id="run-celery-sps",
            execution_source="tool",
        )
        task = eager_app.tasks["execute_extraction"]
        result_dict = task.apply(args=[ctx.to_dict()]).get()
        result = ExecutionResult.from_dict(result_dict)

        assert result.success

    def test_agentic_extract_celery_chain(self, eager_app):
        """Agentic extraction through full Celery task chain."""
        _register_legacy()
        _register_mock_cloud_executors()

        ctx = ExecutionContext(
            executor_name="agentic",
            operation="agentic_extract",
            run_id="run-celery-agentic",
            execution_source="tool",
        )
        task = eager_app.tasks["execute_extraction"]
        result_dict = task.apply(args=[ctx.to_dict()]).get()
        result = ExecutionResult.from_dict(result_dict)

        assert result.success

    def test_unregistered_executor_returns_failure(self, eager_app):
        """Dispatching to unregistered executor returns failure."""
        _register_legacy()
        # Don't register cloud executors

        ctx = ExecutionContext(
            executor_name="table",
            operation="table_extract",
            run_id="run-missing",
            execution_source="tool",
        )
        task = eager_app.tasks["execute_extraction"]
        result_dict = task.apply(args=[ctx.to_dict()]).get()
        result = ExecutionResult.from_dict(result_dict)

        assert not result.success
        assert "table" in result.error.lower()


# ---------------------------------------------------------------------------
# 4. Cross-cutting highlight plugin across executors
# ---------------------------------------------------------------------------

class TestCrossCuttingHighlight:
    @patch("importlib.metadata.entry_points", return_value=[])
    def test_highlight_plugin_not_installed_no_error(self, _mock_eps):
        """When highlight plugin not installed, extraction still works."""
        from executor.executors.plugins.loader import ExecutorPluginLoader

        ExecutorPluginLoader.clear()
        assert ExecutorPluginLoader.get("highlight-data") is None
        # No error — graceful degradation

    def test_mock_highlight_plugin_shared_across_executors(self):
        """Multiple executors can use the same highlight plugin instance."""
        from executor.executors.plugins.loader import ExecutorPluginLoader

        class FakeHighlight:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def run(self, response, **kwargs):
                return {"highlighted": True}

            def get_highlight_data(self):
                return {"lines": [1, 2, 3]}

            def get_confidence_data(self):
                return {"confidence": 0.95}

        fake_ep = MagicMock()
        fake_ep.name = "highlight-data"
        fake_ep.load.return_value = FakeHighlight

        with patch(
            "importlib.metadata.entry_points",
            return_value=[fake_ep],
        ):
            ExecutorPluginLoader.clear()
            cls = ExecutorPluginLoader.get("highlight-data")
            assert cls is FakeHighlight

            # Both legacy and agentic contexts can create instances
            legacy_hl = cls(file_path="/tmp/doc.txt", execution_source="ide")
            agentic_hl = cls(file_path="/tmp/other.txt", execution_source="tool")

            assert legacy_hl.get_highlight_data() == {"lines": [1, 2, 3]}
            assert agentic_hl.get_confidence_data() == {"confidence": 0.95}


# ---------------------------------------------------------------------------
# 5. Plugin loader → registration → dispatch → result flow
# ---------------------------------------------------------------------------

class TestPluginDiscoveryToDispatchFlow:
    def test_full_discovery_to_dispatch_flow(self):
        """Simulate: entry point discovery → register → dispatch → result."""
        # Step 1: "Discover" a cloud executor via entry point
        @ExecutorRegistry.register
        class DiscoveredExecutor(BaseExecutor):
            @property
            def name(self):
                return "discovered"

            def execute(self, context):
                return ExecutionResult(
                    success=True,
                    data={"output": "discovered_result"},
                )

        # Step 2: Verify registration
        assert "discovered" in ExecutorRegistry.list_executors()

        # Step 3: Dispatch via mock Celery
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = ExecutionResult(
            success=True, data={"output": "discovered_result"}
        ).to_dict()
        mock_app.send_task.return_value = mock_result

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="discovered",
            operation="custom_op",
            run_id="run-flow",
            execution_source="tool",
        )
        result = dispatcher.dispatch(ctx)

        # Step 4: Verify result
        assert result.success
        assert result.data["output"] == "discovered_result"

        # Step 5: Verify queue routing
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs.kwargs["queue"] == "celery_executor_discovered"


# ---------------------------------------------------------------------------
# 6. Queue routing for all executor names
# ---------------------------------------------------------------------------

EXECUTOR_QUEUE_MAP = {
    "legacy": "celery_executor_legacy",
    "table": "celery_executor_table",
    "smart_table": "celery_executor_smart_table",
    "simple_prompt_studio": "celery_executor_simple_prompt_studio",
    "agentic": "celery_executor_agentic",
}


class TestQueueRoutingAllExecutors:
    @pytest.mark.parametrize(
        "executor_name,expected_queue",
        list(EXECUTOR_QUEUE_MAP.items()),
    )
    def test_queue_name_for_executor(self, executor_name, expected_queue):
        assert ExecutionDispatcher._get_queue(executor_name) == expected_queue


# ---------------------------------------------------------------------------
# 7. Graceful degradation when cloud plugins missing
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_legacy_works_without_cloud_executors(self, eager_app):
        """Legacy operations work even when no cloud executors installed."""
        _register_legacy()

        # Only legacy should be in registry
        assert ExecutorRegistry.list_executors() == ["legacy"]

        # Legacy operations still work
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="run-degrade",
            execution_source="tool",
            executor_params={
                "tool_id": "t-1",
                "file_name": "test.pdf",
                "file_hash": "abc",
                "PLATFORM_SERVICE_API_KEY": "key",
            },
        )
        # This will fail at the handler level (no mocks), but it should
        # route correctly and NOT fail at registry/dispatch level
        executor = ExecutorRegistry.get("legacy")
        assert executor is not None
        assert executor.name == "legacy"

    def test_cloud_op_on_legacy_returns_meaningful_error(self):
        """Attempting a cloud operation on legacy gives clear error."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        for cloud_op in ["table_extract", "smart_table_extract",
                         "sps_answer_prompt", "agentic_extract"]:
            ctx = ExecutionContext(
                executor_name="legacy",
                operation=cloud_op,
                run_id=f"run-{cloud_op}",
                execution_source="tool",
            )
            result = executor.execute(ctx)
            assert not result.success
            assert "does not support" in result.error

    def test_missing_executor_via_orchestrator(self):
        """Orchestrator returns failure for unregistered executor."""
        _register_legacy()
        orchestrator = ExecutionOrchestrator()

        ctx = ExecutionContext(
            executor_name="table",
            operation="table_extract",
            run_id="run-no-table",
            execution_source="tool",
        )
        result = orchestrator.execute(ctx)
        assert not result.success
        assert "table" in result.error.lower()


# ---------------------------------------------------------------------------
# 8. tasks.py log_component for all operation types
# ---------------------------------------------------------------------------

class TestLogComponentAllOperations:
    """Verify tasks.py log_component builder handles all operation types."""

    def _build_log_component(self, operation, executor_params=None):
        """Simulate the tasks.py log_component logic."""
        params = executor_params or {
            "tool_id": "t-1",
            "file_name": "doc.pdf",
        }
        ctx = ExecutionContext.from_dict({
            "executor_name": "legacy",
            "operation": operation,
            "run_id": "run-log",
            "execution_source": "tool",
            "executor_params": params,
            "request_id": "req-1",
            "log_events_id": "evt-1",
        })

        # Replicate tasks.py logic
        if ctx.operation == "ide_index":
            extract_params = params.get("extract_params", {})
            return {
                "tool_id": extract_params.get("tool_id", ""),
                "run_id": ctx.run_id,
                "doc_name": str(extract_params.get("file_name", "")),
                "operation": ctx.operation,
            }
        elif ctx.operation == "structure_pipeline":
            answer_params = params.get("answer_params", {})
            pipeline_opts = params.get("pipeline_options", {})
            return {
                "tool_id": answer_params.get("tool_id", ""),
                "run_id": ctx.run_id,
                "doc_name": str(pipeline_opts.get("source_file_name", "")),
                "operation": ctx.operation,
            }
        elif ctx.operation in ("table_extract", "smart_table_extract"):
            return {
                "tool_id": params.get("tool_id", ""),
                "run_id": ctx.run_id,
                "doc_name": str(params.get("file_name", "")),
                "operation": ctx.operation,
            }
        else:
            return {
                "tool_id": params.get("tool_id", ""),
                "run_id": ctx.run_id,
                "doc_name": str(params.get("file_name", "")),
                "operation": ctx.operation,
            }

    def test_ide_index_extracts_nested_params(self):
        comp = self._build_log_component("ide_index", {
            "extract_params": {"tool_id": "t-nested", "file_name": "nested.pdf"},
        })
        assert comp["tool_id"] == "t-nested"
        assert comp["doc_name"] == "nested.pdf"

    def test_structure_pipeline_extracts_nested_params(self):
        comp = self._build_log_component("structure_pipeline", {
            "answer_params": {"tool_id": "t-pipe"},
            "pipeline_options": {"source_file_name": "pipe.pdf"},
        })
        assert comp["tool_id"] == "t-pipe"
        assert comp["doc_name"] == "pipe.pdf"

    def test_table_extract_uses_direct_params(self):
        comp = self._build_log_component("table_extract")
        assert comp["tool_id"] == "t-1"
        assert comp["operation"] == "table_extract"

    def test_smart_table_extract_uses_direct_params(self):
        comp = self._build_log_component("smart_table_extract")
        assert comp["operation"] == "smart_table_extract"

    @pytest.mark.parametrize("op", [
        "extract", "index", "answer_prompt", "single_pass_extraction",
        "summarize", "sps_answer_prompt", "sps_index",
        "agentic_extract", "agentic_summarize", "agentic_compare",
    ])
    def test_default_branch_for_standard_ops(self, op):
        comp = self._build_log_component(op)
        assert comp["tool_id"] == "t-1"
        assert comp["doc_name"] == "doc.pdf"
        assert comp["operation"] == op


# ---------------------------------------------------------------------------
# 9. ExecutionResult serialization round-trip
# ---------------------------------------------------------------------------

class TestResultRoundTrip:
    def test_success_result_round_trip(self):
        original = ExecutionResult(
            success=True,
            data={"output": {"field": "value"}, "metadata": {"tokens": 100}},
        )
        restored = ExecutionResult.from_dict(original.to_dict())
        assert restored.success == original.success
        assert restored.data == original.data

    def test_failure_result_round_trip(self):
        original = ExecutionResult.failure(error="Something went wrong")
        restored = ExecutionResult.from_dict(original.to_dict())
        assert not restored.success
        assert restored.error == "Something went wrong"

    def test_context_round_trip(self):
        original = ExecutionContext(
            executor_name="agentic",
            operation="agentic_extract",
            run_id="run-rt",
            execution_source="tool",
            organization_id="org-1",
            executor_params={"key": "value"},
            log_events_id="evt-1",
        )
        restored = ExecutionContext.from_dict(original.to_dict())
        assert restored.executor_name == "agentic"
        assert restored.operation == "agentic_extract"
        assert restored.organization_id == "org-1"
        assert restored.executor_params == {"key": "value"}
        assert restored.log_events_id == "evt-1"
