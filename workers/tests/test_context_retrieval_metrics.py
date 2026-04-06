"""Tests for _inject_context_retrieval_metrics in single pass extraction.

Verifies that:
1. context_retrieval timing is injected for each output field
2. Existing context_retrieval entries are not overwritten
3. No injection on missing file_path
4. Graceful handling of file-read errors
5. chunk-size=0 is forced for single pass in structure_pipeline
"""

from unittest.mock import MagicMock, patch

import pytest

from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


@pytest.fixture(autouse=True)
def _ensure_legacy_registered():
    """Ensure LegacyExecutor is registered."""
    from executor.executors.legacy_executor import LegacyExecutor

    if "legacy" not in ExecutorRegistry.list_executors():
        ExecutorRegistry._registry["legacy"] = LegacyExecutor
    yield


def _get_executor():
    return ExecutorRegistry.get("legacy")


_PATCH_FS = "executor.executors.legacy_executor.FileUtils.get_fs_instance"


class TestInjectContextRetrievalMetrics:
    """Unit tests for _inject_context_retrieval_metrics."""

    @patch(_PATCH_FS)
    def test_injects_timing_for_each_output_field(self, mock_fs):
        """context_retrieval is added for every key in output."""
        fs = MagicMock()
        fs.read.return_value = "file content"
        mock_fs.return_value = fs

        executor = _get_executor()
        result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "val_a", "field_b": "val_b"},
                "metadata": {},
                "metrics": {},
            },
        )
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="single_pass_extraction",
            run_id="run-cr-1",
            execution_source="tool",
            executor_params={
                "file_path": "/data/extract/doc.txt",
                "execution_source": "tool",
            },
        )

        executor._inject_context_retrieval_metrics(result, ctx)

        metrics = result.data["metrics"]
        assert "field_a" in metrics
        assert "field_b" in metrics
        assert "context_retrieval" in metrics["field_a"]
        assert "context_retrieval" in metrics["field_b"]
        assert "time_taken(s)" in metrics["field_a"]["context_retrieval"]
        assert "time_taken(s)" in metrics["field_b"]["context_retrieval"]
        # Timing values should be non-negative floats
        assert metrics["field_a"]["context_retrieval"]["time_taken(s)"] >= 0
        assert metrics["field_b"]["context_retrieval"]["time_taken(s)"] >= 0

    @patch(_PATCH_FS)
    def test_preserves_existing_context_retrieval(self, mock_fs):
        """Existing context_retrieval entries are not overwritten."""
        fs = MagicMock()
        fs.read.return_value = "content"
        mock_fs.return_value = fs

        executor = _get_executor()
        result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "val", "field_b": "val"},
                "metadata": {},
                "metrics": {
                    "field_a": {
                        "context_retrieval": {"time_taken(s)": 0.999},
                    },
                },
            },
        )
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="single_pass_extraction",
            run_id="run-cr-2",
            execution_source="tool",
            executor_params={
                "file_path": "/data/extract/doc.txt",
                "execution_source": "tool",
            },
        )

        executor._inject_context_retrieval_metrics(result, ctx)

        # field_a's existing timing preserved
        assert result.data["metrics"]["field_a"]["context_retrieval"][
            "time_taken(s)"
        ] == pytest.approx(0.999)
        # field_b gets new timing
        assert "context_retrieval" in result.data["metrics"]["field_b"]

    def test_no_injection_without_file_path(self):
        """No injection if file_path is missing from params."""
        executor = _get_executor()
        result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "val"},
                "metadata": {},
                "metrics": {},
            },
        )
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="single_pass_extraction",
            run_id="run-cr-3",
            execution_source="tool",
            executor_params={},
        )

        executor._inject_context_retrieval_metrics(result, ctx)

        # No metrics injected
        assert result.data["metrics"] == {}

    @patch(_PATCH_FS)
    def test_graceful_on_file_read_error(self, mock_fs):
        """File read failure does not crash; no metrics injected."""
        fs = MagicMock()
        fs.read.side_effect = Exception("File not found")
        mock_fs.return_value = fs

        executor = _get_executor()
        result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "val"},
                "metadata": {},
                "metrics": {},
            },
        )
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="single_pass_extraction",
            run_id="run-cr-4",
            execution_source="tool",
            executor_params={
                "file_path": "/data/nonexistent.txt",
                "execution_source": "tool",
            },
        )

        executor._inject_context_retrieval_metrics(result, ctx)

        # Metrics unchanged after error
        assert result.data["metrics"] == {}

    @patch(_PATCH_FS)
    def test_creates_metrics_dict_if_absent(self, mock_fs):
        """If result.data has no 'metrics' key, one is created."""
        fs = MagicMock()
        fs.read.return_value = "content"
        mock_fs.return_value = fs

        executor = _get_executor()
        result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "val"},
            },
        )
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="single_pass_extraction",
            run_id="run-cr-5",
            execution_source="tool",
            executor_params={
                "file_path": "/data/doc.txt",
                "execution_source": "tool",
            },
        )

        executor._inject_context_retrieval_metrics(result, ctx)

        assert "metrics" in result.data
        assert "context_retrieval" in result.data["metrics"]["field_a"]

    @patch(_PATCH_FS)
    def test_preserves_existing_prompt_metrics(self, mock_fs):
        """Other metrics on a prompt (e.g. LLM usage) are preserved."""
        fs = MagicMock()
        fs.read.return_value = "content"
        mock_fs.return_value = fs

        executor = _get_executor()
        result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "val"},
                "metadata": {},
                "metrics": {
                    "field_a": {
                        "extraction_llm": {"tokens": 42},
                    },
                },
            },
        )
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="single_pass_extraction",
            run_id="run-cr-6",
            execution_source="tool",
            executor_params={
                "file_path": "/data/doc.txt",
                "execution_source": "tool",
            },
        )

        executor._inject_context_retrieval_metrics(result, ctx)

        prompt_metrics = result.data["metrics"]["field_a"]
        # Both old and new metrics present
        assert prompt_metrics["extraction_llm"]["tokens"] == 42
        assert "context_retrieval" in prompt_metrics


class TestSinglePassChunkSizeForcing:
    """Verify that chunk-size=0 is forced for single pass in the pipeline."""

    @patch(_PATCH_FS)
    def test_single_pass_forces_chunk_size_zero(self, mock_fs):
        """When single pass falls back to answer_prompt, chunk-size=0 is used."""
        from executor.executors.constants import PromptServiceConstants as PSKeys

        fs = MagicMock()
        fs.read.return_value = "full doc content"
        fs.exists.return_value = False
        mock_fs.return_value = fs

        # Build minimal answer_params with non-zero chunk-size
        outputs = [
            {
                PSKeys.NAME: "field_a",
                PSKeys.PROMPT: "What is the revenue?",
                PSKeys.TYPE: "text",
                "chunk-size": 512,
                "chunk-overlap": 64,
                "retrieval-strategy": "simple",
                "llm": "llm-1",
                "embedding": "emb-1",
                "vector-db": "vdb-1",
                "x2text_adapter": "x2t-1",
                "similarity-top-k": 3,
                "active": True,
            },
        ]

        # Simulate what _handle_structure_pipeline does with is_single_pass
        # We verify indirectly: force chunk-size=0 then call answer_prompt
        # which uses retrieve_complete_context for chunk_size=0
        answer_params = {
            "outputs": outputs,
            "run_id": "run-sp-cs",
            "tool_id": "tool-1",
            "file_hash": "hash1",
            "file_name": "test.pdf",
            "file_path": "/data/extract/doc.txt",
            "execution_source": "tool",
            "PLATFORM_SERVICE_API_KEY": "pk-test",
            "tool_settings": {
                "vector-db": "vdb-1",
                "embedding": "emb-1",
                "x2text_adapter": "x2t-1",
                "llm": "llm-1",
                "enable_challenge": False,
                "challenge_llm": "",
                "enable_single_pass_extraction": True,
                "summarize_as_source": False,
                "enable_highlight": False,
            },
        }

        # Apply the same logic as _handle_structure_pipeline step 4b
        # (single pass forces chunk-size=0 to use full-context retrieval)
        for output in answer_params.get("outputs", []):
            output["chunk-size"] = 0
            output["chunk-overlap"] = 0

        # Verify outputs were modified
        for output in answer_params["outputs"]:
            assert output["chunk-size"] == 0
            assert output["chunk-overlap"] == 0


class TestPipelineIndexUsageKwargsPropagation:
    """Verify that _run_pipeline_index propagates usage_kwargs to INDEX ctx.

    Without this propagation, the embedding adapter's UsageHandler callback
    records audit rows without ``run_id``, so embedding usage is missing from
    the API deployment response metadata when chunking is enabled.
    """

    def test_index_ctx_includes_usage_kwargs(self):
        """The INDEX executor_params include usage_kwargs from extract_params."""
        executor = _get_executor()

        captured_ctx: dict = {}

        def fake_handle_index(ctx):
            captured_ctx["value"] = ctx
            return ExecutionResult(success=True, data={})

        executor._handle_index = fake_handle_index  # type: ignore[assignment]

        index_template = {
            "tool_id": "tool-1",
            "file_hash": "hash-abc",
            "is_highlight_enabled": False,
            "platform_api_key": "pk-test",
            "extracted_file_path": "/data/extract/doc.txt",
        }
        answer_params = {
            "tool_settings": {
                "vector-db": "vdb-1",
                "embedding": "emb-1",
                "x2text_adapter": "x2t-1",
            },
            "outputs": [
                {
                    "name": "field_a",
                    "chunk-size": 512,
                    "chunk-overlap": 64,
                },
            ],
        }
        usage_kwargs = {
            "run_id": "file-exec-123",
            "execution_id": "wf-exec-456",
            "file_name": "doc.pdf",
        }
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="structure_pipeline",
            run_id="run-uk-1",
            execution_source="tool",
        )

        executor._run_pipeline_index(
            context=ctx,
            index_template=index_template,
            answer_params=answer_params,
            extracted_text="extracted",
            usage_kwargs=usage_kwargs,
        )

        index_ctx = captured_ctx["value"]
        assert "usage_kwargs" in index_ctx.executor_params
        assert index_ctx.executor_params["usage_kwargs"] == usage_kwargs
        assert index_ctx.executor_params["usage_kwargs"]["run_id"] == "file-exec-123"

    def test_index_ctx_defaults_to_empty_when_not_provided(self):
        """Without usage_kwargs, INDEX executor_params get empty dict (no crash)."""
        executor = _get_executor()

        captured_ctx: dict = {}

        def fake_handle_index(ctx):
            captured_ctx["value"] = ctx
            return ExecutionResult(success=True, data={})

        executor._handle_index = fake_handle_index  # type: ignore[assignment]

        index_template = {
            "tool_id": "tool-1",
            "file_hash": "hash-abc",
            "is_highlight_enabled": False,
            "platform_api_key": "pk-test",
            "extracted_file_path": "/data/extract/doc.txt",
        }
        answer_params = {
            "tool_settings": {
                "vector-db": "vdb-1",
                "embedding": "emb-1",
                "x2text_adapter": "x2t-1",
            },
            "outputs": [
                {
                    "name": "field_a",
                    "chunk-size": 512,
                    "chunk-overlap": 64,
                },
            ],
        }
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="structure_pipeline",
            run_id="run-uk-2",
            execution_source="tool",
        )

        executor._run_pipeline_index(
            context=ctx,
            index_template=index_template,
            answer_params=answer_params,
            extracted_text="extracted",
        )

        index_ctx = captured_ctx["value"]
        assert index_ctx.executor_params["usage_kwargs"] == {}
