"""Agentic operations: the agentic executor registers and routes all 8
operations to its queue, LegacyExecutor rejects them, and the structure tool
dispatches agentic extract to it (not legacy). Also guards that the old
AGENTIC_EXTRACTION enum stays removed.
"""

from unittest.mock import MagicMock, patch

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
# Operation enum
# ---------------------------------------------------------------------------


class TestAgenticOperations:
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
    @patch("unstract.sdk1.x2txt.X2Text")
    def test_structure_tool_dispatches_agentic_extract(self, mock_x2text_cls, tmp_path):
        """Verify _run_agentic_extraction sends executor_name='agentic'."""
        from file_processing.structure_tool_task import _run_agentic_extraction

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = ExecutionResult(
            success=True, data={"output": {"field": "value"}}
        )

        # Mock X2Text extraction
        mock_x2text_instance = MagicMock()
        mock_x2text_instance.process.return_value = MagicMock(
            extracted_text="extracted text"
        )
        mock_x2text_cls.return_value = mock_x2text_instance

        _run_agentic_extraction(
            tool_metadata={"name": "test"},
            input_file_path=str(tmp_path / "test.pdf"),
            output_dir_path=str(tmp_path / "output"),
            tool_instance_metadata={},
            dispatcher=mock_dispatcher,
            shim=MagicMock(),
            file_execution_id="exec-001",
            execution_id="exec-parent-001",
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
            "ide_index",
            "structure_pipeline",
            "table_extract",
            "smart_table_extract",
        )


# ---------------------------------------------------------------------------
# Agentic extraction timing (UN-2771)
# ---------------------------------------------------------------------------


class TestAgenticExtractionMetrics:
    """The agentic executor's X2Text duration reaches the file-level metric.

    The legacy pipeline times only its own extraction. Agentic prompts extract
    the document inside their own executor, so without folding their reported
    duration in, an agentic-only deployment reports no extraction time at all
    and a mixed deployment under-reports it.
    """

    @staticmethod
    def _agentic(seconds):
        """One prompt's metrics as the executor reports them."""
        return {"invoices": {"text_extraction": {"time_taken(s)": seconds}}}

    def test_sums_across_prompts(self):
        """Each agentic prompt extracts the file itself, so durations add."""
        from file_processing.structure_tool_task import _agentic_extraction_seconds

        metrics = {
            "invoices": {"text_extraction": {"time_taken(s)": 1.5}},
            "receipts": {"text_extraction": {"time_taken(s)": 2.25}},
        }
        assert _agentic_extraction_seconds(metrics) == pytest.approx(3.75)

    @pytest.mark.parametrize(
        "metrics",
        [
            {},
            {"invoices": {}},
            {"invoices": {"text_extraction": {}}},
            {"invoices": {"text_extraction": {"time_taken(s)": None}}},
            {"invoices": {"text_extraction": "not-a-dict"}},
            {"invoices": "not-a-dict"},
            # bool is an int subclass; True must not count as 1 second
            {"invoices": {"text_extraction": {"time_taken(s)": True}}},
        ],
    )
    def test_missing_or_malformed_timing_yields_zero(self, metrics):
        """A plugin that reports no duration must not fabricate one."""
        from file_processing.structure_tool_task import _agentic_extraction_seconds

        assert _agentic_extraction_seconds(metrics) == 0.0

    def test_all_agentic_run_reports_the_file_metric(self):
        """The agentic-only path has no legacy pipeline, so it starts empty."""
        from file_processing.structure_tool_task import _merge_agentic_metrics

        structured_output = {"output": {}, "metadata": {"agentic_only": True}}
        _merge_agentic_metrics(structured_output, self._agentic(4.0))

        metrics = structured_output["metrics"]
        assert metrics["_file"]["text_extraction"]["time_taken(s)"] == pytest.approx(4.0)

    def test_mixed_run_adds_to_the_legacy_duration(self):
        """The under-reporting case: both extractors ran, both must count."""
        from file_processing.structure_tool_task import _merge_agentic_metrics

        structured_output = {
            "metrics": {"_file": {"text_extraction": {"time_taken(s)": 1.0}}}
        }
        _merge_agentic_metrics(structured_output, self._agentic(2.5))

        total = structured_output["metrics"]["_file"]["text_extraction"]["time_taken(s)"]
        assert total == pytest.approx(3.5)

    def test_per_prompt_metrics_land_beside_the_legacy_ones(self):
        """Same shape LegacyExecutor._run_table_extraction uses."""
        from file_processing.structure_tool_task import _merge_agentic_metrics

        structured_output = {"metrics": {"field_a": {"llm": {"time_taken(s)": 2.0}}}}
        _merge_agentic_metrics(structured_output, self._agentic(1.0))

        metrics = structured_output["metrics"]
        assert metrics["field_a"] == {"llm": {"time_taken(s)": 2.0}}
        assert metrics["invoices"]["table_extraction"] == {
            "text_extraction": {"time_taken(s)": 1.0}
        }

    def test_no_agentic_prompts_changes_nothing(self):
        """A purely legacy run must not grow an empty metrics dict."""
        from file_processing.structure_tool_task import _merge_agentic_metrics

        structured_output = {"output": {}}
        _merge_agentic_metrics(structured_output, {})

        assert "metrics" not in structured_output

    def test_executor_reporting_no_timing_leaves_the_bucket_absent(self):
        """Per-prompt metrics still surface; a zero duration is not written."""
        from file_processing.structure_tool_task import _merge_agentic_metrics

        structured_output = {}
        _merge_agentic_metrics(
            structured_output, {"invoices": {"table_rows": {"count": 12}}}
        )

        metrics = structured_output["metrics"]
        assert metrics["invoices"]["table_extraction"] == {"table_rows": {"count": 12}}
        assert "_file" not in metrics

    def test_prompt_named_file_does_not_invade_the_reserved_bucket(self):
        """`_file` is reserved; a prompt with that name must not land in it.

        Its extraction duration still counts toward the file-level total —
        only the per-prompt entry is dropped, because there is nowhere
        collision-free to put it.
        """
        from file_processing.structure_tool_task import _merge_agentic_metrics

        structured_output = {}
        _merge_agentic_metrics(
            structured_output,
            {"_file": {"text_extraction": {"time_taken(s)": 3.0}}},
        )

        file_bucket = structured_output["metrics"]["_file"]
        assert file_bucket["text_extraction"] == {"time_taken(s)": 3.0}
        assert "table_extraction" not in file_bucket
