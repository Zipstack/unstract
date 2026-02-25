"""Phase 5D — Tests for structure_pipeline compound operation.

Tests _handle_structure_pipeline in LegacyExecutor which runs the full
extract → summarize → index → answer_prompt pipeline in a single
executor invocation.
"""

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.result import ExecutionResult

# ---------------------------------------------------------------------------
# Patch targets — all at source in executor.executors.legacy_executor
# ---------------------------------------------------------------------------

_PATCH_FILE_UTILS = "executor.executors.file_utils.FileUtils.get_fs_instance"
_PATCH_INDEXING_DEPS = (
    "executor.executors.legacy_executor.LegacyExecutor._get_indexing_deps"
)
_PATCH_PROMPT_DEPS = (
    "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def executor():
    """Create a LegacyExecutor instance."""
    from executor.executors.legacy_executor import LegacyExecutor

    return LegacyExecutor()


@pytest.fixture
def mock_fs():
    """Mock filesystem."""
    fs = MagicMock(name="file_storage")
    fs.exists.return_value = False
    fs.read.return_value = ""
    fs.write.return_value = None
    fs.get_hash_from_file.return_value = "hash123"
    return fs


def _make_pipeline_context(
    executor_params: dict,
    run_id: str = "run-1",
    organization_id: str = "org-1",
) -> ExecutionContext:
    """Build a structure_pipeline ExecutionContext."""
    return ExecutionContext(
        executor_name="legacy",
        operation=Operation.STRUCTURE_PIPELINE.value,
        run_id=run_id,
        execution_source="tool",
        organization_id=organization_id,
        request_id="req-1",
        executor_params=executor_params,
    )


def _base_extract_params() -> dict:
    """Extract params template."""
    return {
        "x2text_instance_id": "x2t-1",
        "file_path": "/data/test.pdf",
        "enable_highlight": False,
        "output_file_path": "/data/exec/EXTRACT",
        "platform_api_key": "sk-test",
        "usage_kwargs": {"run_id": "run-1", "file_name": "test.pdf"},
    }


def _base_index_template() -> dict:
    """Index template."""
    return {
        "tool_id": "tool-1",
        "file_hash": "hash-abc",
        "is_highlight_enabled": False,
        "platform_api_key": "sk-test",
        "extracted_file_path": "/data/exec/EXTRACT",
    }


def _base_answer_params() -> dict:
    """Answer params (payload for answer_prompt)."""
    return {
        "run_id": "run-1",
        "tool_settings": {
            "vector-db": "vdb-1",
            "embedding": "emb-1",
            "x2text_adapter": "x2t-1",
            "llm": "llm-1",
            "challenge_llm": "",
            "enable_challenge": False,
            "enable_single_pass_extraction": False,
            "summarize_as_source": False,
            "enable_highlight": False,
        },
        "outputs": [
            {
                "name": "field_a",
                "prompt": "What is the revenue?",
                "type": "text",
                "active": True,
                "chunk-size": 512,
                "chunk-overlap": 128,
                "llm": "llm-1",
                "embedding": "emb-1",
                "vector-db": "vdb-1",
                "x2text_adapter": "x2t-1",
                "retrieval-strategy": "simple",
                "similarity-top-k": 5,
            },
        ],
        "tool_id": "tool-1",
        "file_hash": "hash-abc",
        "file_name": "test.pdf",
        "file_path": "/data/exec/EXTRACT",
        "execution_source": "tool",
        "custom_data": {},
        "PLATFORM_SERVICE_API_KEY": "sk-test",
    }


def _base_pipeline_options() -> dict:
    """Default pipeline options."""
    return {
        "skip_extraction_and_indexing": False,
        "is_summarization_enabled": False,
        "is_single_pass_enabled": False,
        "input_file_path": "/data/test.pdf",
        "source_file_name": "test.pdf",
    }


# ---------------------------------------------------------------------------
# Tests — Operation enum and routing
# ---------------------------------------------------------------------------


class TestStructurePipelineEnum:
    """Verify enum and operation map registration."""

    def test_operation_enum_exists(self):
        assert Operation.STRUCTURE_PIPELINE.value == "structure_pipeline"

    def test_operation_map_has_structure_pipeline(self, executor):
        assert "structure_pipeline" in executor._OPERATION_MAP


# ---------------------------------------------------------------------------
# Tests — Normal pipeline: extract → index → answer_prompt
# ---------------------------------------------------------------------------


class TestNormalPipeline:
    """Normal pipeline: extract + index + answer_prompt."""

    def test_extract_index_answer(self, executor):
        """Full pipeline calls extract, index, and answer_prompt."""
        extract_result = ExecutionResult(
            success=True, data={"extracted_text": "Revenue is $1M"}
        )
        index_result = ExecutionResult(
            success=True, data={"doc_id": "doc-1"}
        )
        answer_result = ExecutionResult(
            success=True,
            data={
                "output": {"field_a": "$1M"},
                "metadata": {},
                "metrics": {"field_a": {"llm": {"time_taken(s)": 1.0}}},
            },
        )

        executor._handle_extract = MagicMock(return_value=extract_result)
        executor._handle_index = MagicMock(return_value=index_result)
        executor._handle_answer_prompt = MagicMock(
            return_value=answer_result
        )

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": _base_pipeline_options(),
        })

        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        assert executor._handle_extract.call_count == 1
        assert executor._handle_index.call_count == 1
        assert executor._handle_answer_prompt.call_count == 1

    def test_result_has_metadata_and_file_name(self, executor):
        """Result includes source_file_name in metadata."""
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_index = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"doc_id": "d1"}
            )
        )
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}, "metadata": {}}
            )
        )

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": _base_pipeline_options(),
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        assert result.data["metadata"]["file_name"] == "test.pdf"

    def test_extracted_text_in_metadata(self, executor):
        """Extracted text is added to result metadata."""
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "Revenue $1M"}
            )
        )
        executor._handle_index = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"doc_id": "d1"}
            )
        )
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": _base_pipeline_options(),
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.data["metadata"]["extracted_text"] == "Revenue $1M"

    def test_index_metrics_merged(self, executor):
        """Index metrics are merged into answer metrics."""
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_index = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"doc_id": "d1"}
            )
        )
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True,
                data={
                    "output": {},
                    "metrics": {
                        "field_a": {"llm": {"time_taken(s)": 2.0}},
                    },
                },
            )
        )
        # Simulate index metrics by patching _run_pipeline_index
        executor._run_pipeline_index = MagicMock(
            return_value={
                "field_a": {"indexing": {"time_taken(s)": 0.5}},
            }
        )

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": _base_pipeline_options(),
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        metrics = result.data["metrics"]
        # Both llm and indexing metrics for field_a should be merged
        assert "llm" in metrics["field_a"]
        assert "indexing" in metrics["field_a"]


# ---------------------------------------------------------------------------
# Tests — Extract failure propagation
# ---------------------------------------------------------------------------


class TestExtractFailure:
    """Extract failure stops the pipeline."""

    def test_extract_failure_stops_pipeline(self, executor):
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult.failure(error="x2text error")
        )
        executor._handle_index = MagicMock()
        executor._handle_answer_prompt = MagicMock()

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": _base_pipeline_options(),
        })
        result = executor._handle_structure_pipeline(ctx)

        assert not result.success
        assert "x2text error" in result.error
        executor._handle_index.assert_not_called()
        executor._handle_answer_prompt.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — Skip extraction (smart table)
# ---------------------------------------------------------------------------


class TestSkipExtraction:
    """Smart table: skip extract+index, use source file."""

    def test_skip_extraction_uses_input_file(self, executor):
        executor._handle_extract = MagicMock()
        executor._handle_index = MagicMock()
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        opts = _base_pipeline_options()
        opts["skip_extraction_and_indexing"] = True
        answer = _base_answer_params()

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": answer,
            "pipeline_options": opts,
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        executor._handle_extract.assert_not_called()
        executor._handle_index.assert_not_called()
        # file_path should be set to input_file_path
        call_ctx = executor._handle_answer_prompt.call_args[0][0]
        assert call_ctx.executor_params["file_path"] == "/data/test.pdf"

    def test_skip_extraction_table_settings_injection(self, executor):
        """Table settings get input_file when extraction is skipped."""
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        opts = _base_pipeline_options()
        opts["skip_extraction_and_indexing"] = True
        answer = _base_answer_params()
        answer["outputs"][0]["table_settings"] = {
            "is_directory_mode": False,
        }

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": answer,
            "pipeline_options": opts,
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        ts = answer["outputs"][0]["table_settings"]
        assert ts["input_file"] == "/data/test.pdf"


# ---------------------------------------------------------------------------
# Tests — Single pass extraction
# ---------------------------------------------------------------------------


class TestSinglePass:
    """Single pass: extract + answer_prompt (no indexing)."""

    def test_single_pass_skips_index(self, executor):
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_index = MagicMock()
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        opts = _base_pipeline_options()
        opts["is_single_pass_enabled"] = True

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": opts,
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        executor._handle_extract.assert_called_once()
        executor._handle_index.assert_not_called()
        executor._handle_answer_prompt.assert_called_once()

    def test_single_pass_operation_is_single_pass(self, executor):
        """The answer_prompt call uses single_pass_extraction operation."""
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        opts = _base_pipeline_options()
        opts["is_single_pass_enabled"] = True

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": opts,
        })
        executor._handle_structure_pipeline(ctx)

        call_ctx = executor._handle_answer_prompt.call_args[0][0]
        assert call_ctx.operation == "single_pass_extraction"


# ---------------------------------------------------------------------------
# Tests — Summarize pipeline
# ---------------------------------------------------------------------------


class TestSummarizePipeline:
    """Summarize: extract + summarize + answer_prompt (no indexing)."""

    @patch(_PATCH_FILE_UTILS)
    def test_summarize_calls_handle_summarize(
        self, mock_get_fs, executor, mock_fs
    ):
        mock_get_fs.return_value = mock_fs
        mock_fs.exists.return_value = False
        mock_fs.read.return_value = "extracted text for summarize"

        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_summarize = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"data": "summarized text"}
            )
        )
        executor._handle_index = MagicMock()
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        opts = _base_pipeline_options()
        opts["is_summarization_enabled"] = True

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": opts,
            "summarize_params": {
                "llm_adapter_instance_id": "llm-1",
                "summarize_prompt": "Summarize this",
                "extract_file_path": "/data/exec/EXTRACT",
                "summarize_file_path": "/data/exec/SUMMARIZE",
                "platform_api_key": "sk-test",
                "prompt_keys": ["field_a"],
            },
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        executor._handle_summarize.assert_called_once()
        executor._handle_index.assert_not_called()

    @patch(_PATCH_FILE_UTILS)
    def test_summarize_uses_cache(self, mock_get_fs, executor, mock_fs):
        """If cached summary exists, _handle_summarize is NOT called."""
        mock_get_fs.return_value = mock_fs
        mock_fs.exists.return_value = True
        mock_fs.read.return_value = "cached summary"

        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_summarize = MagicMock()
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        opts = _base_pipeline_options()
        opts["is_summarization_enabled"] = True

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": opts,
            "summarize_params": {
                "llm_adapter_instance_id": "llm-1",
                "summarize_prompt": "Summarize this",
                "extract_file_path": "/data/exec/EXTRACT",
                "summarize_file_path": "/data/exec/SUMMARIZE",
                "platform_api_key": "sk-test",
                "prompt_keys": ["field_a"],
            },
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        executor._handle_summarize.assert_not_called()

    @patch(_PATCH_FILE_UTILS)
    def test_summarize_updates_answer_params(
        self, mock_get_fs, executor, mock_fs
    ):
        """After summarize, answer_params file_path and hash are updated."""
        mock_get_fs.return_value = mock_fs
        mock_fs.exists.return_value = False
        mock_fs.read.return_value = "doc text"
        mock_fs.get_hash_from_file.return_value = "sum-hash-456"

        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_summarize = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"data": "summarized"}
            )
        )
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        answer = _base_answer_params()
        opts = _base_pipeline_options()
        opts["is_summarization_enabled"] = True

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": answer,
            "pipeline_options": opts,
            "summarize_params": {
                "llm_adapter_instance_id": "llm-1",
                "summarize_prompt": "Summarize",
                "extract_file_path": "/data/exec/EXTRACT",
                "summarize_file_path": "/data/exec/SUMMARIZE",
                "platform_api_key": "sk-test",
                "prompt_keys": [],
            },
        })
        executor._handle_structure_pipeline(ctx)

        # Check answer_params were updated
        assert answer["file_hash"] == "sum-hash-456"
        assert answer["file_path"] == "/data/exec/SUMMARIZE"

    @patch(_PATCH_FILE_UTILS)
    def test_summarize_sets_chunk_size_zero(
        self, mock_get_fs, executor, mock_fs
    ):
        """Summarize sets chunk-size=0 for all outputs."""
        mock_get_fs.return_value = mock_fs
        mock_fs.exists.return_value = True
        mock_fs.read.return_value = "cached"

        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "t"}
            )
        )
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        answer = _base_answer_params()
        opts = _base_pipeline_options()
        opts["is_summarization_enabled"] = True

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": answer,
            "pipeline_options": opts,
            "summarize_params": {
                "llm_adapter_instance_id": "llm-1",
                "summarize_prompt": "Summarize",
                "extract_file_path": "/data/exec/EXTRACT",
                "summarize_file_path": "/data/exec/SUMMARIZE",
                "platform_api_key": "sk-test",
                "prompt_keys": [],
            },
        })
        executor._handle_structure_pipeline(ctx)

        # Outputs should have chunk-size=0
        for output in answer["outputs"]:
            assert output["chunk-size"] == 0
            assert output["chunk-overlap"] == 0


# ---------------------------------------------------------------------------
# Tests — Index dedup
# ---------------------------------------------------------------------------


class TestIndexDedup:
    """Index step deduplication."""

    def test_index_dedup_skips_duplicate_params(self, executor):
        """Duplicate param combos are only indexed once."""
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        index_call_count = 0
        original_index = executor._handle_index

        def counting_index(ctx):
            nonlocal index_call_count
            index_call_count += 1
            return ExecutionResult(success=True, data={"doc_id": "d1"})

        executor._handle_index = counting_index
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        answer = _base_answer_params()
        # Add a second output with same adapter params
        answer["outputs"].append({
            "name": "field_b",
            "prompt": "What is the profit?",
            "type": "text",
            "active": True,
            "chunk-size": 512,
            "chunk-overlap": 128,
            "llm": "llm-1",
            "embedding": "emb-1",
            "vector-db": "vdb-1",
            "x2text_adapter": "x2t-1",
        })

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": answer,
            "pipeline_options": _base_pipeline_options(),
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        # Only one index call despite two outputs (same params)
        assert index_call_count == 1

    def test_index_different_params_indexes_both(self, executor):
        """Different param combos are indexed separately."""
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        index_call_count = 0

        def counting_index(ctx):
            nonlocal index_call_count
            index_call_count += 1
            return ExecutionResult(success=True, data={"doc_id": "d1"})

        executor._handle_index = counting_index
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        answer = _base_answer_params()
        answer["outputs"].append({
            "name": "field_b",
            "prompt": "What is the profit?",
            "type": "text",
            "active": True,
            "chunk-size": 256,  # Different chunk size
            "chunk-overlap": 64,
            "llm": "llm-1",
            "embedding": "emb-1",
            "vector-db": "vdb-1",
            "x2text_adapter": "x2t-1",
        })

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": answer,
            "pipeline_options": _base_pipeline_options(),
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        assert index_call_count == 2

    def test_chunk_size_zero_skips_index(self, executor):
        """chunk-size=0 outputs skip indexing entirely."""
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_index = MagicMock()
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        answer = _base_answer_params()
        answer["outputs"][0]["chunk-size"] = 0

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": answer,
            "pipeline_options": _base_pipeline_options(),
        })
        result = executor._handle_structure_pipeline(ctx)

        assert result.success
        executor._handle_index.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — Answer prompt failure
# ---------------------------------------------------------------------------


class TestAnswerPromptFailure:
    """Answer prompt failure propagates correctly."""

    def test_answer_failure_propagates(self, executor):
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_index = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"doc_id": "d1"}
            )
        )
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult.failure(error="LLM timeout")
        )

        ctx = _make_pipeline_context({
            "extract_params": _base_extract_params(),
            "index_template": _base_index_template(),
            "answer_params": _base_answer_params(),
            "pipeline_options": _base_pipeline_options(),
        })
        result = executor._handle_structure_pipeline(ctx)

        assert not result.success
        assert "LLM timeout" in result.error


# ---------------------------------------------------------------------------
# Tests — Merge metrics utility
# ---------------------------------------------------------------------------


class TestMergeMetrics:
    """Test _merge_pipeline_metrics."""

    def test_merge_disjoint(self, executor):
        m = executor._merge_pipeline_metrics(
            {"a": {"x": 1}}, {"b": {"y": 2}}
        )
        assert m == {"a": {"x": 1}, "b": {"y": 2}}

    def test_merge_overlapping(self, executor):
        m = executor._merge_pipeline_metrics(
            {"a": {"x": 1}}, {"a": {"y": 2}}
        )
        assert m == {"a": {"x": 1, "y": 2}}

    def test_merge_non_dict_values(self, executor):
        m = executor._merge_pipeline_metrics(
            {"a": 1}, {"b": 2}
        )
        assert m == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# Tests — Sub-context creation
# ---------------------------------------------------------------------------


class TestSubContextCreation:
    """Verify sub-contexts inherit parent context fields."""

    def test_extract_context_inherits_fields(self, executor):
        """Extract sub-context gets run_id, org_id, etc. from parent."""
        executor._handle_extract = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"extracted_text": "text"}
            )
        )
        executor._handle_index = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"doc_id": "d1"}
            )
        )
        executor._handle_answer_prompt = MagicMock(
            return_value=ExecutionResult(
                success=True, data={"output": {}}
            )
        )

        ctx = _make_pipeline_context(
            {
                "extract_params": _base_extract_params(),
                "index_template": _base_index_template(),
                "answer_params": _base_answer_params(),
                "pipeline_options": _base_pipeline_options(),
            },
            run_id="custom-run",
            organization_id="custom-org",
        )
        executor._handle_structure_pipeline(ctx)

        extract_ctx = executor._handle_extract.call_args[0][0]
        assert extract_ctx.run_id == "custom-run"
        assert extract_ctx.organization_id == "custom-org"
        assert extract_ctx.operation == "extract"

        index_ctx = executor._handle_index.call_args[0][0]
        assert index_ctx.run_id == "custom-run"
        assert index_ctx.operation == "index"

        answer_ctx = executor._handle_answer_prompt.call_args[0][0]
        assert answer_ctx.run_id == "custom-run"
        assert answer_ctx.operation == "answer_prompt"
