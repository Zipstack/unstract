"""Phase 2-SANITY — Full-chain integration tests for LegacyExecutor.

All Phase 2 code and unit tests are complete (2A–2H, 194 workers tests).
This file bridges unit tests and real integration by testing the full
Celery chain:

    task.apply() → execute_extraction task → ExecutionOrchestrator
    → ExecutorRegistry.get("legacy") → LegacyExecutor.execute()
    → _handle_X() → ExecutionResult

All in Celery eager mode (no broker needed). External adapters
(X2Text, LLM, VectorDB) are mocked.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from executor.executors.constants import (
    IndexingConstants as IKeys,
    PromptServiceConstants as PSKeys,
)
from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_PATCH_X2TEXT = "executor.executors.legacy_executor.X2Text"
_PATCH_FS = "executor.executors.legacy_executor.FileUtils.get_fs_instance"
_PATCH_INDEX_DEPS = (
    "executor.executors.legacy_executor.LegacyExecutor._get_indexing_deps"
)
_PATCH_PROMPT_DEPS = (
    "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
)
_PATCH_SHIM = "executor.executors.legacy_executor.ExecutorToolShim"
_PATCH_RUN_COMPLETION = (
    "executor.executors.answer_prompt.AnswerPromptService.run_completion"
)
_PATCH_INDEX_UTILS = (
    "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key"
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ensure_legacy_registered():
    """Ensure LegacyExecutor is registered without clearing other state.

    Unlike unit tests that clear() + re-register, sanity tests need
    LegacyExecutor always present. We add it idempotently.
    """
    from executor.executors.legacy_executor import LegacyExecutor

    if "legacy" not in ExecutorRegistry.list_executors():
        ExecutorRegistry._registry["legacy"] = LegacyExecutor
    yield


@pytest.fixture
def eager_app():
    """Configure the real executor Celery app for eager-mode testing."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_task(eager_app, ctx_dict):
    """Run execute_extraction task via task.apply() (eager-safe)."""
    task = eager_app.tasks["execute_extraction"]
    result = task.apply(args=[ctx_dict])
    return result.get()


def _mock_llm(answer="sanity answer"):
    """Create a mock LLM matching the test_answer_prompt.py pattern."""
    llm = MagicMock(name="llm")
    response = MagicMock()
    response.text = answer
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


def _mock_prompt_deps(llm=None):
    """Return a 7-tuple matching _get_prompt_deps() return shape.

    Uses the real AnswerPromptService + mocked adapters.
    """
    if llm is None:
        llm = _mock_llm()

    from executor.executors.answer_prompt import AnswerPromptService

    RetrievalService = MagicMock(name="RetrievalService")
    RetrievalService.run_retrieval.return_value = ["chunk1", "chunk2"]
    RetrievalService.retrieve_complete_context.return_value = ["full content"]

    VariableReplacementService = MagicMock(name="VariableReplacementService")
    VariableReplacementService.is_variables_present.return_value = False

    Index = MagicMock(name="Index")
    index_instance = MagicMock()
    index_instance.generate_index_key.return_value = "doc-id-sanity"
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


def _mock_process_response(text="sanity extracted text"):
    """Build a mock TextExtractionResult."""
    from unstract.sdk1.adapters.x2text.dto import (
        TextExtractionMetadata,
        TextExtractionResult,
    )

    metadata = TextExtractionMetadata(whisper_hash="sanity-hash")
    return TextExtractionResult(
        extracted_text=text,
        extraction_metadata=metadata,
    )


def _make_prompt(name="field_a", prompt="What is the revenue?",
                 output_type="text", **overrides):
    """Build a minimal prompt definition dict."""
    d = {
        PSKeys.NAME: name,
        PSKeys.PROMPT: prompt,
        PSKeys.TYPE: output_type,
        PSKeys.CHUNK_SIZE: 512,
        PSKeys.CHUNK_OVERLAP: 128,
        PSKeys.RETRIEVAL_STRATEGY: "simple",
        PSKeys.LLM: "llm-1",
        PSKeys.EMBEDDING: "emb-1",
        PSKeys.VECTOR_DB: "vdb-1",
        PSKeys.X2TEXT_ADAPTER: "x2t-1",
        PSKeys.SIMILARITY_TOP_K: 5,
    }
    d.update(overrides)
    return d


# --- Context factories per operation ---


def _extract_ctx(**overrides):
    defaults = {
        "executor_name": "legacy",
        "operation": "extract",
        "run_id": "run-sanity-ext",
        "execution_source": "tool",
        "organization_id": "org-test",
        "executor_params": {
            "x2text_instance_id": "x2t-sanity",
            "file_path": "/data/sanity.pdf",
            "platform_api_key": "sk-sanity",
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _index_ctx(**overrides):
    defaults = {
        "executor_name": "legacy",
        "operation": "index",
        "run_id": "run-sanity-idx",
        "execution_source": "tool",
        "organization_id": "org-test",
        "executor_params": {
            "embedding_instance_id": "emb-sanity",
            "vector_db_instance_id": "vdb-sanity",
            "x2text_instance_id": "x2t-sanity",
            "file_path": "/data/sanity.pdf",
            "file_hash": "sanity-hash",
            "extracted_text": "Sanity test document text",
            "platform_api_key": "sk-sanity",
            "chunk_size": 512,
            "chunk_overlap": 128,
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _answer_prompt_ctx(prompts=None, **overrides):
    if prompts is None:
        prompts = [_make_prompt()]
    defaults = {
        "executor_name": "legacy",
        "operation": Operation.ANSWER_PROMPT.value,
        "run_id": "run-sanity-ap",
        "execution_source": "ide",
        "executor_params": {
            PSKeys.OUTPUTS: prompts,
            PSKeys.TOOL_SETTINGS: {},
            PSKeys.TOOL_ID: "tool-sanity",
            PSKeys.EXECUTION_ID: "exec-sanity",
            PSKeys.FILE_HASH: "hash-sanity",
            PSKeys.FILE_PATH: "/data/sanity.txt",
            PSKeys.FILE_NAME: "sanity.txt",
            PSKeys.LOG_EVENTS_ID: "",
            PSKeys.CUSTOM_DATA: {},
            PSKeys.EXECUTION_SOURCE: "ide",
            PSKeys.PLATFORM_SERVICE_API_KEY: "pk-sanity",
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _summarize_ctx(**overrides):
    defaults = {
        "executor_name": "legacy",
        "operation": "summarize",
        "run_id": "run-sanity-sum",
        "execution_source": "tool",
        "executor_params": {
            "llm_adapter_instance_id": "llm-sanity",
            "summarize_prompt": "Summarize the document.",
            "context": "Long document content here.",
            "prompt_keys": ["invoice_number", "total"],
            "PLATFORM_SERVICE_API_KEY": "pk-sanity",
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


# ===========================================================================
# Test classes
# ===========================================================================


class TestSanityExtract:
    """Full-chain extract tests through Celery eager mode."""

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_extract_full_chain(self, mock_x2text_cls, mock_get_fs, eager_app):
        """Mocked X2Text + FileUtils → result.data has extracted_text."""
        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response(
            "sanity extracted"
        )
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _extract_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data[IKeys.EXTRACTED_TEXT] == "sanity extracted"

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_extract_missing_params_full_chain(
        self, mock_x2text_cls, mock_get_fs, eager_app
    ):
        """Empty params → failure with missing fields message."""
        ctx = _extract_ctx(executor_params={"platform_api_key": "sk-test"})
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "x2text_instance_id" in result.error
        assert "file_path" in result.error

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_extract_adapter_error_full_chain(
        self, mock_x2text_cls, mock_get_fs, eager_app
    ):
        """X2Text raises AdapterError → failure result, no unhandled exception."""
        from unstract.sdk1.adapters.exceptions import AdapterError

        mock_x2text = MagicMock()
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text.x2text_instance.get_name.return_value = "SanityExtractor"
        mock_x2text.process.side_effect = AdapterError("sanity adapter err")
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _extract_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "SanityExtractor" in result.error
        assert "sanity adapter err" in result.error


class TestSanityIndex:
    """Full-chain index tests through Celery eager mode."""

    @patch(_PATCH_FS)
    @patch(_PATCH_INDEX_DEPS)
    def test_index_full_chain(self, mock_deps, mock_get_fs, eager_app):
        """Mocked _get_indexing_deps → result.data has doc_id."""
        mock_index_cls = MagicMock()
        mock_index = MagicMock()
        mock_index.generate_index_key.return_value = "doc-sanity-idx"
        mock_index.is_document_indexed.return_value = False
        mock_index.perform_indexing.return_value = "doc-sanity-idx"
        mock_index_cls.return_value = mock_index

        mock_emb_cls = MagicMock()
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls = MagicMock()
        mock_vdb_cls.return_value = MagicMock()

        mock_deps.return_value = (mock_index_cls, mock_emb_cls, mock_vdb_cls)
        mock_get_fs.return_value = MagicMock()

        ctx = _index_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data[IKeys.DOC_ID] == "doc-sanity-idx"

    @patch(_PATCH_INDEX_UTILS, return_value="doc-zero-chunk-sanity")
    @patch(_PATCH_FS)
    def test_index_chunk_size_zero_full_chain(
        self, mock_get_fs, mock_gen_key, eager_app
    ):
        """chunk_size=0 skips heavy deps → returns doc_id via IndexingUtils."""
        mock_get_fs.return_value = MagicMock()

        params = {
            "embedding_instance_id": "emb-sanity",
            "vector_db_instance_id": "vdb-sanity",
            "x2text_instance_id": "x2t-sanity",
            "file_path": "/data/sanity.pdf",
            "file_hash": "sanity-hash",
            "extracted_text": "text",
            "platform_api_key": "sk-sanity",
            "chunk_size": 0,
            "chunk_overlap": 0,
        }
        ctx = _index_ctx(executor_params=params)
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data[IKeys.DOC_ID] == "doc-zero-chunk-sanity"

    @patch(_PATCH_FS)
    @patch(_PATCH_INDEX_DEPS)
    def test_index_error_full_chain(self, mock_deps, mock_get_fs, eager_app):
        """perform_indexing raises → failure result."""
        mock_index_cls = MagicMock()
        mock_index = MagicMock()
        mock_index.generate_index_key.return_value = "doc-err"
        mock_index.is_document_indexed.return_value = False
        mock_index.perform_indexing.side_effect = RuntimeError("VDB down")
        mock_index_cls.return_value = mock_index

        mock_emb_cls = MagicMock()
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls = MagicMock()
        mock_vdb_cls.return_value = MagicMock()

        mock_deps.return_value = (mock_index_cls, mock_emb_cls, mock_vdb_cls)
        mock_get_fs.return_value = MagicMock()

        ctx = _index_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "indexing" in result.error.lower()


class TestSanityAnswerPrompt:
    """Full-chain answer_prompt tests through Celery eager mode."""

    @patch(_PATCH_INDEX_UTILS, return_value="doc-id-sanity")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_answer_prompt_text_full_chain(
        self, mock_shim_cls, mock_deps, _mock_idx, eager_app
    ):
        """TEXT prompt → result.data has output, metadata, metrics."""
        llm = _mock_llm("sanity answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _answer_prompt_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert PSKeys.OUTPUT in result.data
        assert PSKeys.METADATA in result.data
        assert PSKeys.METRICS in result.data
        assert result.data[PSKeys.OUTPUT]["field_a"] == "sanity answer"

    @patch(_PATCH_INDEX_UTILS, return_value="doc-id-sanity")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_answer_prompt_multi_prompt_full_chain(
        self, mock_shim_cls, mock_deps, _mock_idx, eager_app
    ):
        """Two prompts → both field names in output and metrics."""
        llm = _mock_llm("multi answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        prompts = [
            _make_prompt(name="revenue"),
            _make_prompt(name="date_signed"),
        ]
        ctx = _answer_prompt_ctx(prompts=prompts)
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert "revenue" in result.data[PSKeys.OUTPUT]
        assert "date_signed" in result.data[PSKeys.OUTPUT]
        assert "revenue" in result.data[PSKeys.METRICS]
        assert "date_signed" in result.data[PSKeys.METRICS]

    @patch(_PATCH_INDEX_UTILS, return_value="doc-id-sanity")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_answer_prompt_table_fails_full_chain(
        self, mock_shim_cls, mock_deps, _mock_idx, eager_app
    ):
        """TABLE type → failure mentioning TABLE."""
        llm = _mock_llm()
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _answer_prompt_ctx(
            prompts=[_make_prompt(output_type="table")]
        )
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "TABLE" in result.error


class TestSanitySinglePass:
    """Full-chain single_pass_extraction test."""

    @patch(_PATCH_INDEX_UTILS, return_value="doc-id-sanity")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_single_pass_delegates_full_chain(
        self, mock_shim_cls, mock_deps, _mock_idx, eager_app
    ):
        """Same mocks as answer_prompt → same response shape."""
        llm = _mock_llm("single pass answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _answer_prompt_ctx(
            operation=Operation.SINGLE_PASS_EXTRACTION.value,
        )
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert PSKeys.OUTPUT in result.data
        assert result.data[PSKeys.OUTPUT]["field_a"] == "single pass answer"


class TestSanitySummarize:
    """Full-chain summarize tests through Celery eager mode."""

    @patch(_PATCH_RUN_COMPLETION, return_value="Sanity summary text.")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_summarize_full_chain(
        self, mock_shim_cls, mock_get_deps, mock_run, eager_app
    ):
        """Mocked _get_prompt_deps + run_completion → result.data has summary."""
        mock_llm_cls = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        mock_get_deps.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            mock_llm_cls, MagicMock(), MagicMock(),
        )

        ctx = _summarize_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data["data"] == "Sanity summary text."

    def test_summarize_missing_llm_full_chain(self, eager_app):
        """Missing llm_adapter_instance_id → failure."""
        ctx = _summarize_ctx(
            executor_params={
                "llm_adapter_instance_id": "",
                "summarize_prompt": "Summarize.",
                "context": "Document text.",
                "PLATFORM_SERVICE_API_KEY": "pk-test",
            }
        )
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "llm_adapter_instance_id" in result.error

    @patch(_PATCH_RUN_COMPLETION, side_effect=Exception("LLM down"))
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_summarize_error_full_chain(
        self, mock_shim_cls, mock_get_deps, mock_run, eager_app
    ):
        """run_completion raises → failure mentioning summarization."""
        mock_llm_cls = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        mock_get_deps.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            mock_llm_cls, MagicMock(), MagicMock(),
        )

        ctx = _summarize_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "summarization" in result.error.lower() or "LLM" in result.error


class TestSanityAgenticExtraction:
    """Full-chain agentic_extraction test."""

    def test_agentic_extraction_fails_full_chain(self, eager_app):
        """No mocks needed → failure mentioning agentic and plugin."""
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="agentic_extraction",
            run_id="run-sanity-agentic",
            execution_source="tool",
        )
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "agentic" in result.error.lower()
        assert "plugin" in result.error.lower()


class TestSanityResponseContracts:
    """Verify response dicts survive JSON round-trip with expected keys."""

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_extract_contract(self, mock_x2text_cls, mock_get_fs, eager_app):
        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response("contract")
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _extract_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())

        # JSON round-trip
        serialized = json.dumps(result_dict)
        deserialized = json.loads(serialized)
        result = ExecutionResult.from_dict(deserialized)

        assert result.success is True
        assert isinstance(result.data[IKeys.EXTRACTED_TEXT], str)

    @patch(_PATCH_FS)
    @patch(_PATCH_INDEX_DEPS)
    def test_index_contract(self, mock_deps, mock_get_fs, eager_app):
        mock_index_cls = MagicMock()
        mock_index = MagicMock()
        mock_index.generate_index_key.return_value = "doc-contract"
        mock_index.is_document_indexed.return_value = False
        mock_index.perform_indexing.return_value = "doc-contract"
        mock_index_cls.return_value = mock_index

        mock_emb_cls = MagicMock()
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls = MagicMock()
        mock_vdb_cls.return_value = MagicMock()

        mock_deps.return_value = (mock_index_cls, mock_emb_cls, mock_vdb_cls)
        mock_get_fs.return_value = MagicMock()

        ctx = _index_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())

        serialized = json.dumps(result_dict)
        deserialized = json.loads(serialized)
        result = ExecutionResult.from_dict(deserialized)

        assert result.success is True
        assert isinstance(result.data[IKeys.DOC_ID], str)

    @patch(_PATCH_INDEX_UTILS, return_value="doc-id-sanity")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_answer_prompt_contract(
        self, mock_shim_cls, mock_deps, _mock_idx, eager_app
    ):
        llm = _mock_llm("contract answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _answer_prompt_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())

        serialized = json.dumps(result_dict)
        deserialized = json.loads(serialized)
        result = ExecutionResult.from_dict(deserialized)

        assert result.success is True
        assert isinstance(result.data[PSKeys.OUTPUT], dict)
        assert isinstance(result.data[PSKeys.METADATA], dict)
        assert isinstance(result.data[PSKeys.METRICS], dict)

    @patch(_PATCH_RUN_COMPLETION, return_value="contract summary")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_summarize_contract(
        self, mock_shim_cls, mock_get_deps, mock_run, eager_app
    ):
        mock_llm_cls = MagicMock()
        mock_llm_cls.return_value = MagicMock()
        mock_get_deps.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            mock_llm_cls, MagicMock(), MagicMock(),
        )

        ctx = _summarize_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())

        serialized = json.dumps(result_dict)
        deserialized = json.loads(serialized)
        result = ExecutionResult.from_dict(deserialized)

        assert result.success is True
        assert isinstance(result.data["data"], str)


class TestSanityDispatcher:
    """Full-chain dispatcher tests with Celery eager mode."""

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_dispatcher_dispatch_full_chain(
        self, mock_x2text_cls, mock_get_fs, eager_app
    ):
        """ExecutionDispatcher dispatches through Celery and returns result.

        Celery's ``send_task`` doesn't reliably use eager mode, so we
        patch it to route through ``task.apply()`` instead — this still
        exercises the full Dispatcher → task → orchestrator chain.
        """
        from unstract.sdk1.execution.dispatcher import ExecutionDispatcher

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response("dispatched")
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        task = eager_app.tasks["execute_extraction"]

        def eager_send_task(name, args=None, **kwargs):
            return task.apply(args=args)

        with patch.object(eager_app, "send_task", side_effect=eager_send_task):
            dispatcher = ExecutionDispatcher(celery_app=eager_app)
            ctx = _extract_ctx()
            result = dispatcher.dispatch(ctx, timeout=10)

        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert result.data[IKeys.EXTRACTED_TEXT] == "dispatched"

    def test_dispatcher_no_app_raises(self):
        """ExecutionDispatcher(celery_app=None).dispatch() → ValueError."""
        from unstract.sdk1.execution.dispatcher import ExecutionDispatcher

        dispatcher = ExecutionDispatcher(celery_app=None)
        ctx = _extract_ctx()

        with pytest.raises(ValueError, match="No Celery app"):
            dispatcher.dispatch(ctx)


class TestSanityCrossCutting:
    """Cross-cutting concerns: unknown ops, invalid contexts, error round-trip."""

    def test_unknown_operation_full_chain(self, eager_app):
        """operation='nonexistent' → failure mentioning unsupported."""
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="nonexistent",
            run_id="run-sanity-unknown",
            execution_source="tool",
        )
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "nonexistent" in result.error.lower()

    def test_invalid_context_dict_full_chain(self, eager_app):
        """Malformed dict → failure mentioning 'Invalid execution context'."""
        result_dict = _run_task(eager_app, {"bad": "data"})
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "Invalid execution context" in result.error

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_failure_result_json_round_trip(
        self, mock_x2text_cls, mock_get_fs, eager_app
    ):
        """Failure result survives JSON serialization with error preserved."""
        from unstract.sdk1.adapters.exceptions import AdapterError

        mock_x2text = MagicMock()
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text.x2text_instance.get_name.return_value = "FailExtractor"
        mock_x2text.process.side_effect = AdapterError("round trip error")
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _extract_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())

        # Verify raw dict survives JSON round-trip
        serialized = json.dumps(result_dict)
        deserialized = json.loads(serialized)
        result = ExecutionResult.from_dict(deserialized)

        assert result.success is False
        assert "round trip error" in result.error
        assert "FailExtractor" in result.error
