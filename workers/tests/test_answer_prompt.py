"""Tests for the answer_prompt pipeline (Phase 2E).

Tests the _handle_answer_prompt method, AnswerPromptService,
VariableReplacementService, and type conversion logic.
All heavy dependencies (LLM, VectorDB, etc.) are mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

from executor.executors.constants import (
    PromptServiceConstants as PSKeys,
    RetrievalStrategy,
)
from executor.executors.exceptions import LegacyExecutorError
from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.result import ExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prompt(
    name: str = "field_a",
    prompt: str = "What is the revenue?",
    output_type: str = "text",
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    retrieval_strategy: str = "simple",
    llm_id: str = "llm-1",
    embedding_id: str = "emb-1",
    vector_db_id: str = "vdb-1",
    x2text_id: str = "x2t-1",
    similarity_top_k: int = 5,
):
    """Build a minimal prompt definition dict."""
    return {
        PSKeys.NAME: name,
        PSKeys.PROMPT: prompt,
        PSKeys.TYPE: output_type,
        PSKeys.CHUNK_SIZE: chunk_size,
        PSKeys.CHUNK_OVERLAP: chunk_overlap,
        PSKeys.RETRIEVAL_STRATEGY: retrieval_strategy,
        PSKeys.LLM: llm_id,
        PSKeys.EMBEDDING: embedding_id,
        PSKeys.VECTOR_DB: vector_db_id,
        PSKeys.X2TEXT_ADAPTER: x2text_id,
        PSKeys.SIMILARITY_TOP_K: similarity_top_k,
    }


def _make_context(
    prompts=None,
    tool_settings=None,
    file_hash="abc123",
    file_path="/data/doc.txt",
    file_name="doc.txt",
    execution_source="ide",
    platform_api_key="pk-test",
    run_id="run-1",
):
    """Build an ExecutionContext for answer_prompt."""
    if prompts is None:
        prompts = [_make_prompt()]
    if tool_settings is None:
        tool_settings = {}

    params = {
        PSKeys.OUTPUTS: prompts,
        PSKeys.TOOL_SETTINGS: tool_settings,
        PSKeys.TOOL_ID: "tool-1",
        PSKeys.EXECUTION_ID: "exec-1",
        PSKeys.FILE_HASH: file_hash,
        PSKeys.FILE_PATH: file_path,
        PSKeys.FILE_NAME: file_name,
        PSKeys.LOG_EVENTS_ID: "",
        PSKeys.CUSTOM_DATA: {},
        PSKeys.EXECUTION_SOURCE: execution_source,
        PSKeys.PLATFORM_SERVICE_API_KEY: platform_api_key,
    }
    return ExecutionContext(
        executor_name="legacy",
        operation=Operation.ANSWER_PROMPT.value,
        executor_params=params,
        run_id=run_id,
        execution_source=execution_source,
    )


def _mock_llm():
    """Create a mock LLM that returns a configurable answer."""
    llm = MagicMock(name="llm")
    response = MagicMock()
    response.text = "test answer"
    llm.complete.return_value = {
        PSKeys.RESPONSE: response,
        PSKeys.HIGHLIGHT_DATA: [],
        PSKeys.CONFIDENCE_DATA: None,
        PSKeys.WORD_CONFIDENCE_DATA: None,
        PSKeys.LINE_NUMBERS: [],
        PSKeys.WHISPER_HASH: "",
    }
    llm.get_usage_reason.return_value = "extraction"
    llm.get_metrics.return_value = {"tokens": 100}
    return llm


def _mock_deps(llm=None):
    """Return a tuple of mocked prompt deps matching _get_prompt_deps()."""
    if llm is None:
        llm = _mock_llm()

    # AnswerPromptService — use the real class
    from executor.executors.answer_prompt import AnswerPromptService

    RetrievalService = MagicMock(name="RetrievalService")
    RetrievalService.run_retrieval.return_value = ["chunk1", "chunk2"]
    RetrievalService.retrieve_complete_context.return_value = ["full content"]

    VariableReplacementService = MagicMock(name="VariableReplacementService")
    VariableReplacementService.is_variables_present.return_value = False

    Index = MagicMock(name="Index")
    index_instance = MagicMock()
    index_instance.generate_index_key.return_value = "doc-id-1"
    Index.return_value = index_instance

    LLM_cls = MagicMock(name="LLM")
    LLM_cls.return_value = llm

    EmbeddingCompat = MagicMock(name="EmbeddingCompat")
    VectorDB = MagicMock(name="VectorDB")

    return (
        AnswerPromptService,
        RetrievalService,
        VariableReplacementService,
        Index,
        LLM_cls,
        EmbeddingCompat,
        VectorDB,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PATCH_INDEX_UTILS = (
    "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key"
)


@pytest.fixture(autouse=True)
def _mock_indexing_utils():
    """Mock IndexingUtils.generate_index_key for all answer_prompt tests.

    _handle_answer_prompt calls IndexingUtils.generate_index_key(tool=shim)
    which delegates to PlatformHelper.get_adapter_config() — a real HTTP
    call.  Since tests use a mock shim, the platform URL is invalid.
    """
    with patch(_PATCH_INDEX_UTILS, return_value="doc-id-test"):
        yield


# ---------------------------------------------------------------------------
# Tests — _handle_answer_prompt
# ---------------------------------------------------------------------------

class TestHandleAnswerPromptText:
    """Tests for TEXT type prompts."""

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_text_prompt_returns_success(self, mock_shim_cls, mock_deps):
        """Simple TEXT prompt returns success with structured output."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context()
        result = executor._handle_answer_prompt(ctx)

        assert result.success is True
        assert PSKeys.OUTPUT in result.data
        assert PSKeys.METADATA in result.data
        assert PSKeys.METRICS in result.data
        assert "field_a" in result.data[PSKeys.OUTPUT]

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_text_prompt_answer_stored(self, mock_shim_cls, mock_deps):
        """The LLM answer is stored in structured_output."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context()
        result = executor._handle_answer_prompt(ctx)

        assert result.data[PSKeys.OUTPUT]["field_a"] == "test answer"

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_trailing_newline_stripped(self, mock_shim_cls, mock_deps):
        """Trailing newlines are stripped from text answers."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        response = MagicMock()
        response.text = "answer with trailing\n"
        llm.complete.return_value = {
            PSKeys.RESPONSE: response,
            PSKeys.HIGHLIGHT_DATA: [],
            PSKeys.CONFIDENCE_DATA: None,
            PSKeys.WORD_CONFIDENCE_DATA: None,
            PSKeys.LINE_NUMBERS: [],
            PSKeys.WHISPER_HASH: "",
        }
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        result = executor._handle_answer_prompt(_make_context())

        assert result.data[PSKeys.OUTPUT]["field_a"] == "answer with trailing"


class TestHandleAnswerPromptTypes:
    """Tests for type-specific post-processing."""

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_number_type_converts_to_float(self, mock_shim_cls, mock_deps):
        """NUMBER type converts answer to float."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        # First call: main retrieval answer. Second call: number extraction.
        response1 = MagicMock()
        response1.text = "revenue is $42.5M"
        response2 = MagicMock()
        response2.text = "42500000"
        llm.complete.side_effect = [
            {PSKeys.RESPONSE: response1, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
            {PSKeys.RESPONSE: response2, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
        ]
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(prompts=[_make_prompt(output_type="number")])
        result = executor._handle_answer_prompt(ctx)

        assert result.data[PSKeys.OUTPUT]["field_a"] == 42500000.0

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_number_na_returns_none(self, mock_shim_cls, mock_deps):
        """NUMBER type with NA answer returns None."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        response = MagicMock()
        response.text = "NA"
        llm.complete.return_value = {
            PSKeys.RESPONSE: response, PSKeys.HIGHLIGHT_DATA: [],
            PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
            PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: "",
        }
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(prompts=[_make_prompt(output_type="number")])
        result = executor._handle_answer_prompt(ctx)

        # NA → sanitized to None
        assert result.data[PSKeys.OUTPUT]["field_a"] is None

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_boolean_yes(self, mock_shim_cls, mock_deps):
        """BOOLEAN type converts 'yes' to True."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        response1 = MagicMock()
        response1.text = "The document confirms it"
        response2 = MagicMock()
        response2.text = "yes"
        llm.complete.side_effect = [
            {PSKeys.RESPONSE: response1, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
            {PSKeys.RESPONSE: response2, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
        ]
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(prompts=[_make_prompt(output_type="boolean")])
        result = executor._handle_answer_prompt(ctx)

        assert result.data[PSKeys.OUTPUT]["field_a"] is True

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_boolean_no(self, mock_shim_cls, mock_deps):
        """BOOLEAN type converts 'no' to False."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        response1 = MagicMock()
        response1.text = "not confirmed"
        response2 = MagicMock()
        response2.text = "no"
        llm.complete.side_effect = [
            {PSKeys.RESPONSE: response1, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
            {PSKeys.RESPONSE: response2, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
        ]
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(prompts=[_make_prompt(output_type="boolean")])
        result = executor._handle_answer_prompt(ctx)

        assert result.data[PSKeys.OUTPUT]["field_a"] is False

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_email_type(self, mock_shim_cls, mock_deps):
        """EMAIL type extracts email address."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        response1 = MagicMock()
        response1.text = "Contact: user@example.com"
        response2 = MagicMock()
        response2.text = "user@example.com"
        llm.complete.side_effect = [
            {PSKeys.RESPONSE: response1, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
            {PSKeys.RESPONSE: response2, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
        ]
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(prompts=[_make_prompt(output_type="email")])
        result = executor._handle_answer_prompt(ctx)

        assert result.data[PSKeys.OUTPUT]["field_a"] == "user@example.com"

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_date_type(self, mock_shim_cls, mock_deps):
        """DATE type extracts date in ISO format."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        response1 = MagicMock()
        response1.text = "The date is January 15, 2024"
        response2 = MagicMock()
        response2.text = "2024-01-15"
        llm.complete.side_effect = [
            {PSKeys.RESPONSE: response1, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
            {PSKeys.RESPONSE: response2, PSKeys.HIGHLIGHT_DATA: [],
             PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
             PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: ""},
        ]
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(prompts=[_make_prompt(output_type="date")])
        result = executor._handle_answer_prompt(ctx)

        assert result.data[PSKeys.OUTPUT]["field_a"] == "2024-01-15"


class TestHandleAnswerPromptJSON:
    """Tests for JSON type handling."""

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_json_parsed(self, mock_shim_cls, mock_deps):
        """JSON type parses valid JSON from answer."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        response = MagicMock()
        response.text = '{"key": "value"}'
        llm.complete.return_value = {
            PSKeys.RESPONSE: response, PSKeys.HIGHLIGHT_DATA: [],
            PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
            PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: "",
        }
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(prompts=[_make_prompt(output_type="json")])
        result = executor._handle_answer_prompt(ctx)

        assert result.data[PSKeys.OUTPUT]["field_a"] == {"key": "value"}

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_json_na_returns_none(self, mock_shim_cls, mock_deps):
        """JSON type with NA answer returns None."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        response = MagicMock()
        response.text = "NA"
        llm.complete.return_value = {
            PSKeys.RESPONSE: response, PSKeys.HIGHLIGHT_DATA: [],
            PSKeys.CONFIDENCE_DATA: None, PSKeys.WORD_CONFIDENCE_DATA: None,
            PSKeys.LINE_NUMBERS: [], PSKeys.WHISPER_HASH: "",
        }
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(prompts=[_make_prompt(output_type="json")])
        result = executor._handle_answer_prompt(ctx)

        assert result.data[PSKeys.OUTPUT]["field_a"] is None


class TestHandleAnswerPromptRetrieval:
    """Tests for retrieval integration."""

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_chunked_retrieval_uses_run_retrieval(
        self, mock_shim_cls, mock_deps
    ):
        """chunk_size > 0 uses RetrievalService.run_retrieval."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        deps = _mock_deps(llm)
        _, RetrievalService, *_ = deps
        mock_deps.return_value = deps
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(
            prompts=[_make_prompt(chunk_size=512)]
        )
        result = executor._handle_answer_prompt(ctx)

        RetrievalService.run_retrieval.assert_called_once()
        assert result.success is True

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_complete_context_for_chunk_zero(
        self, mock_shim_cls, mock_deps
    ):
        """chunk_size=0 uses RetrievalService.retrieve_complete_context."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        deps = _mock_deps(llm)
        _, RetrievalService, *_ = deps
        mock_deps.return_value = deps
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(
            prompts=[_make_prompt(chunk_size=0)]
        )
        result = executor._handle_answer_prompt(ctx)

        RetrievalService.retrieve_complete_context.assert_called_once()
        assert result.success is True

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_context_stored_in_metadata(self, mock_shim_cls, mock_deps):
        """Retrieved context is stored in metadata."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        result = executor._handle_answer_prompt(_make_context())

        metadata = result.data[PSKeys.METADATA]
        assert "field_a" in metadata[PSKeys.CONTEXT]

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_invalid_strategy_skips_retrieval(
        self, mock_shim_cls, mock_deps
    ):
        """Invalid retrieval strategy skips retrieval, answer stays NA."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(
            prompts=[_make_prompt(retrieval_strategy="nonexistent")]
        )
        result = executor._handle_answer_prompt(ctx)

        # Answer stays "NA" which gets sanitized to None
        assert result.data[PSKeys.OUTPUT]["field_a"] is None


class TestHandleAnswerPromptMultiPrompt:
    """Tests for multi-prompt processing."""

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_multiple_prompts(self, mock_shim_cls, mock_deps):
        """Multiple prompts are all processed."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        prompts = [
            _make_prompt(name="revenue"),
            _make_prompt(name="date_signed", output_type="text"),
        ]
        executor = LegacyExecutor()
        ctx = _make_context(prompts=prompts)
        result = executor._handle_answer_prompt(ctx)

        output = result.data[PSKeys.OUTPUT]
        assert "revenue" in output
        assert "date_signed" in output


class TestHandleAnswerPromptErrors:
    """Tests for error handling."""

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_table_type_raises_error(self, mock_shim_cls, mock_deps):
        """TABLE type raises LegacyExecutorError (plugins not available)."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(
            prompts=[_make_prompt(output_type="table")]
        )
        # TABLE raises LegacyExecutorError which is caught by execute()
        result = executor.execute(ctx)
        assert result.success is False
        assert "TABLE" in result.error

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_line_item_type_raises_error(self, mock_shim_cls, mock_deps):
        """LINE_ITEM type raises LegacyExecutorError."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        ctx = _make_context(
            prompts=[_make_prompt(output_type="line-item")]
        )
        result = executor.execute(ctx)
        assert result.success is False
        assert "LINE_ITEM" in result.error


class TestHandleAnswerPromptMetrics:
    """Tests for metrics collection."""

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_metrics_collected(self, mock_shim_cls, mock_deps):
        """Metrics include context_retrieval and LLM metrics."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        mock_deps.return_value = _mock_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        result = executor._handle_answer_prompt(_make_context())

        metrics = result.data[PSKeys.METRICS]
        assert "field_a" in metrics
        assert "context_retrieval" in metrics["field_a"]
        assert "extraction_llm" in metrics["field_a"]

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_vectordb_closed(self, mock_shim_cls, mock_deps):
        """VectorDB is closed after processing."""
        from executor.executors.legacy_executor import LegacyExecutor

        llm = _mock_llm()
        deps = _mock_deps(llm)
        mock_deps.return_value = deps
        _, _, _, _, _, _, VectorDB = deps
        vdb_instance = MagicMock()
        VectorDB.return_value = vdb_instance
        mock_shim_cls.return_value = MagicMock()

        executor = LegacyExecutor()
        executor._handle_answer_prompt(_make_context())

        vdb_instance.close.assert_called_once()


class TestNullSanitization:
    """Tests for _sanitize_null_values."""

    def test_na_string_becomes_none(self):
        """Top-level 'NA' string → None."""
        from executor.executors.legacy_executor import LegacyExecutor

        output = {"field": "NA"}
        result = LegacyExecutor._sanitize_null_values(output)
        assert result["field"] is None

    def test_na_case_insensitive(self):
        """'na' (lowercase) → None."""
        from executor.executors.legacy_executor import LegacyExecutor

        output = {"field": "na"}
        result = LegacyExecutor._sanitize_null_values(output)
        assert result["field"] is None

    def test_nested_list_na(self):
        """NA in nested list items → None."""
        from executor.executors.legacy_executor import LegacyExecutor

        output = {"field": ["value", "NA", "other"]}
        result = LegacyExecutor._sanitize_null_values(output)
        assert result["field"] == ["value", None, "other"]

    def test_nested_dict_in_list_na(self):
        """NA in dicts inside lists → None."""
        from executor.executors.legacy_executor import LegacyExecutor

        output = {"field": [{"a": "NA", "b": "ok"}]}
        result = LegacyExecutor._sanitize_null_values(output)
        assert result["field"] == [{"a": None, "b": "ok"}]

    def test_nested_dict_na(self):
        """NA in nested dict values → None."""
        from executor.executors.legacy_executor import LegacyExecutor

        output = {"field": {"a": "NA", "b": "ok"}}
        result = LegacyExecutor._sanitize_null_values(output)
        assert result["field"] == {"a": None, "b": "ok"}

    def test_non_na_values_untouched(self):
        """Non-NA values are not modified."""
        from executor.executors.legacy_executor import LegacyExecutor

        output = {"field": "hello", "num": 42, "flag": True}
        result = LegacyExecutor._sanitize_null_values(output)
        assert result == {"field": "hello", "num": 42, "flag": True}


class TestAnswerPromptServiceUnit:
    """Unit tests for AnswerPromptService methods."""

    def test_extract_variable_replaces_percent_vars(self):
        """Replace %var% references in prompt text."""
        from executor.executors.answer_prompt import AnswerPromptService

        structured = {"field_a": "42"}
        output = {"prompt": "Original: %field_a%"}
        result = AnswerPromptService.extract_variable(
            structured, ["field_a"], output, "Value is %field_a%"
        )
        assert result == "Value is 42"

    def test_extract_variable_missing_raises(self):
        """Missing variable raises ValueError."""
        from executor.executors.answer_prompt import AnswerPromptService

        output = {"prompt": "test"}
        with pytest.raises(ValueError, match="not found"):
            AnswerPromptService.extract_variable(
                {}, ["missing_var"], output, "Value is %missing_var%"
            )

    def test_construct_prompt_includes_all_parts(self):
        """Constructed prompt includes preamble, prompt, postamble, context."""
        from executor.executors.answer_prompt import AnswerPromptService

        result = AnswerPromptService.construct_prompt(
            preamble="You are a helpful assistant",
            prompt="What is the revenue?",
            postamble="Be precise",
            grammar_list=[],
            context="Revenue was $1M",
            platform_postamble="",
            word_confidence_postamble="",
        )
        assert "You are a helpful assistant" in result
        assert "What is the revenue?" in result
        assert "Be precise" in result
        assert "Revenue was $1M" in result
        assert "Answer:" in result

    def test_construct_prompt_with_grammar(self):
        """Grammar list adds synonym notes."""
        from executor.executors.answer_prompt import AnswerPromptService

        result = AnswerPromptService.construct_prompt(
            preamble="",
            prompt="Find the amount",
            postamble="",
            grammar_list=[{"word": "amount", "synonyms": ["sum", "total"]}],
            context="test",
            platform_postamble="",
            word_confidence_postamble="",
        )
        assert "amount" in result
        assert "sum, total" in result


class TestVariableReplacementService:
    """Tests for the VariableReplacementService."""

    def test_is_variables_present_true(self):
        """Detects {{variables}} in text."""
        from executor.executors.variable_replacement import (
            VariableReplacementService,
        )

        assert VariableReplacementService.is_variables_present(
            "Hello {{name}}"
        ) is True

    def test_is_variables_present_false(self):
        """Returns False when no variables present."""
        from executor.executors.variable_replacement import (
            VariableReplacementService,
        )

        assert VariableReplacementService.is_variables_present(
            "Hello world"
        ) is False

    def test_replace_static_variable(self):
        """Static variable {{var}} is replaced with structured output value."""
        from executor.executors.variable_replacement import (
            VariableReplacementHelper,
        )

        result = VariableReplacementHelper.replace_static_variable(
            prompt="Total is {{revenue}}",
            structured_output={"revenue": "$1M"},
            variable="revenue",
        )
        assert result == "Total is $1M"

    def test_custom_data_variable(self):
        """Custom data variable {{custom_data.key}} is replaced."""
        from executor.executors.variable_replacement import (
            VariableReplacementHelper,
        )

        result = VariableReplacementHelper.replace_custom_data_variable(
            prompt="Company: {{custom_data.company_name}}",
            variable="custom_data.company_name",
            custom_data={"company_name": "Acme Inc"},
        )
        assert result == "Company: Acme Inc"

    def test_custom_data_missing_raises(self):
        """Missing custom data key raises CustomDataError."""
        from executor.executors.exceptions import CustomDataError
        from executor.executors.variable_replacement import (
            VariableReplacementHelper,
        )

        with pytest.raises(CustomDataError):
            VariableReplacementHelper.replace_custom_data_variable(
                prompt="{{custom_data.missing}}",
                variable="custom_data.missing",
                custom_data={"other": "value"},
            )
