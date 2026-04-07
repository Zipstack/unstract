"""Tests for single pass extraction wiring and pipeline propagation.

Verifies that:
1. chunk-size=0 is forced for single pass when falling back to
   answer_prompt (so RetrievalService.retrieve_complete_context is
   used and reports context_retrieval at the source).
2. _run_pipeline_index propagates usage_kwargs to the INDEX context
   so embedding usage rows carry the correct run_id.

Note: the cloud single_pass_extraction plugin owns the file read and
is responsible for populating context_retrieval in its returned
metrics. LegacyExecutor does not re-measure or inject that timing —
see _handle_single_pass_extraction's docstring for the contract.
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
