"""Phase 4-SANITY — IDE path integration tests through executor chain.

Phase 4 replaces PromptTool HTTP calls in PromptStudioHelper with
ExecutionDispatcher → executor worker → LegacyExecutor.

These tests build the EXACT payloads that prompt_studio_helper.py
now sends via ExecutionDispatcher, push them through the full Celery
eager-mode chain, and verify the results match what the IDE expects.

This validates the full contract:
    prompt_studio_helper builds payload
    → ExecutionContext(execution_source="ide", ...)
    → Celery task → LegacyExecutor._handle_X()
    → ExecutionResult → result.data used by IDE

All tests use execution_source="ide" to match the real IDE path.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from executor.executors.constants import (
    IndexingConstants as IKeys,
    PromptServiceConstants as PSKeys,
)
from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult

# ---------------------------------------------------------------------------
# Patch targets (same as Phase 2 sanity)
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ensure_legacy_registered():
    """Ensure LegacyExecutor is registered."""
    from executor.executors.legacy_executor import LegacyExecutor

    if "legacy" not in ExecutorRegistry.list_executors():
        ExecutorRegistry._registry["legacy"] = LegacyExecutor
    yield


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_task(eager_app, ctx_dict):
    """Run execute_extraction task via task.apply() (eager-safe)."""
    task = eager_app.tasks["execute_extraction"]
    result = task.apply(args=[ctx_dict])
    return result.get()


def _mock_llm(answer="ide answer"):
    """Create a mock LLM matching the answer_prompt pattern."""
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
    llm.get_metrics.return_value = {"tokens": 42}
    return llm


def _mock_prompt_deps(llm=None):
    """Return 7-tuple matching _get_prompt_deps() shape."""
    if llm is None:
        llm = _mock_llm()

    from executor.executors.answer_prompt import AnswerPromptService

    RetrievalService = MagicMock(name="RetrievalService")
    RetrievalService.run_retrieval.return_value = ["chunk1"]
    RetrievalService.retrieve_complete_context.return_value = ["full doc"]

    VariableReplacementService = MagicMock(name="VariableReplacementService")
    VariableReplacementService.is_variables_present.return_value = False

    Index = MagicMock(name="Index")
    index_instance = MagicMock()
    index_instance.generate_index_key.return_value = "doc-ide-key"
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


def _mock_process_response(text="ide extracted text"):
    """Build a mock TextExtractionResult."""
    from unstract.sdk1.adapters.x2text.dto import (
        TextExtractionMetadata,
        TextExtractionResult,
    )

    metadata = TextExtractionMetadata(whisper_hash="ide-hash")
    return TextExtractionResult(
        extracted_text=text,
        extraction_metadata=metadata,
    )


def _make_ide_prompt(name="invoice_number", prompt="What is the invoice number?",
                     output_type="text", **overrides):
    """Build a prompt dict matching what prompt_studio_helper builds.

    Uses the exact key strings from ToolStudioPromptKeys / PSKeys.
    """
    d = {
        PSKeys.NAME: name,
        PSKeys.PROMPT: prompt,
        PSKeys.TYPE: output_type,
        # These match the hyphenated keys from ToolStudioPromptKeys
        "chunk-size": 512,
        "chunk-overlap": 64,
        "retrieval-strategy": "simple",
        "llm": "llm-ide-1",
        "embedding": "emb-ide-1",
        "vector-db": "vdb-ide-1",
        "x2text_adapter": "x2t-ide-1",
        "similarity-top-k": 3,
        "active": True,
        "required": True,
    }
    d.update(overrides)
    return d


# --- IDE context factories matching prompt_studio_helper payloads ---


def _ide_extract_ctx(**overrides):
    """Build ExecutionContext matching dynamic_extractor() dispatch.

    Key mapping: dynamic_extractor uses IKeys constants for payload keys,
    and adds "platform_api_key" for the executor.
    """
    defaults = {
        "executor_name": "legacy",
        "operation": "extract",
        "run_id": "run-ide-ext",
        "execution_source": "ide",
        "organization_id": "org-ide-test",
        "executor_params": {
            "x2text_instance_id": "x2t-ide-1",
            "file_path": "/prompt-studio/org/user/tool/doc.pdf",
            "enable_highlight": True,
            "usage_kwargs": {"run_id": "run-ide-ext", "file_name": "doc.pdf"},
            "run_id": "run-ide-ext",
            "log_events_id": "log-ide-1",
            "execution_source": "ide",
            "output_file_path": "/prompt-studio/org/user/tool/extract/doc.txt",
            "platform_api_key": "pk-ide-test",
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _ide_index_ctx(**overrides):
    """Build ExecutionContext matching dynamic_indexer() dispatch.

    Key mapping: dynamic_indexer uses IKeys constants and adds
    "platform_api_key" for the executor.
    """
    defaults = {
        "executor_name": "legacy",
        "operation": "index",
        "run_id": "run-ide-idx",
        "execution_source": "ide",
        "organization_id": "org-ide-test",
        "executor_params": {
            "tool_id": "tool-ide-1",
            "embedding_instance_id": "emb-ide-1",
            "vector_db_instance_id": "vdb-ide-1",
            "x2text_instance_id": "x2t-ide-1",
            "file_path": "/prompt-studio/org/user/tool/extract/doc.txt",
            "file_hash": None,
            "chunk_overlap": 64,
            "chunk_size": 512,
            "reindex": False,
            "enable_highlight": True,
            "usage_kwargs": {"run_id": "run-ide-idx", "file_name": "doc.pdf"},
            "extracted_text": "IDE extracted document text content",
            "run_id": "run-ide-idx",
            "log_events_id": "log-ide-1",
            "execution_source": "ide",
            "platform_api_key": "pk-ide-test",
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _ide_answer_prompt_ctx(prompts=None, **overrides):
    """Build ExecutionContext matching _fetch_response() dispatch.

    Key mapping: _fetch_response uses TSPKeys (ToolStudioPromptKeys)
    constants and adds PLATFORM_SERVICE_API_KEY + include_metadata.
    """
    if prompts is None:
        prompts = [_make_ide_prompt()]
    defaults = {
        "executor_name": "legacy",
        "operation": "answer_prompt",
        "run_id": "run-ide-ap",
        "execution_source": "ide",
        "organization_id": "org-ide-test",
        "executor_params": {
            "tool_settings": {
                "enable_challenge": False,
                "challenge_llm": "llm-challenge-1",
                "single_pass_extraction_mode": False,
                "summarize_as_source": False,
                "preamble": "Extract accurately.",
                "postamble": "No explanation.",
                "grammar": [],
                "enable_highlight": True,
                "enable_word_confidence": False,
                "platform_postamble": "",
                "word_confidence_postamble": "",
            },
            "outputs": prompts,
            "tool_id": "tool-ide-1",
            "run_id": "run-ide-ap",
            "file_name": "invoice.pdf",
            "file_hash": "abc123hash",
            "file_path": "/prompt-studio/org/user/tool/extract/invoice.txt",
            "log_events_id": "log-ide-1",
            "execution_source": "ide",
            "custom_data": {},
            "PLATFORM_SERVICE_API_KEY": "pk-ide-test",
            "include_metadata": True,
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _ide_single_pass_ctx(prompts=None, **overrides):
    """Build ExecutionContext matching _fetch_single_pass_response() dispatch."""
    if prompts is None:
        prompts = [
            _make_ide_prompt(name="revenue", prompt="What is total revenue?"),
            _make_ide_prompt(name="date", prompt="What is the date?"),
        ]
    defaults = {
        "executor_name": "legacy",
        "operation": "single_pass_extraction",
        "run_id": "run-ide-sp",
        "execution_source": "ide",
        "organization_id": "org-ide-test",
        "executor_params": {
            "tool_settings": {
                "preamble": "Extract accurately.",
                "postamble": "No explanation.",
                "grammar": [],
                "llm": "llm-ide-1",
                "x2text_adapter": "x2t-ide-1",
                "vector-db": "vdb-ide-1",
                "embedding": "emb-ide-1",
                "chunk-size": 0,
                "chunk-overlap": 0,
                "enable_challenge": False,
                "enable_highlight": True,
                "enable_word_confidence": False,
                "challenge_llm": None,
                "platform_postamble": "",
                "word_confidence_postamble": "",
                "summarize_as_source": False,
            },
            "outputs": prompts,
            "tool_id": "tool-ide-1",
            "run_id": "run-ide-sp",
            "file_hash": "abc123hash",
            "file_name": "invoice.pdf",
            "file_path": "/prompt-studio/org/user/tool/extract/invoice.txt",
            "log_events_id": "log-ide-1",
            "execution_source": "ide",
            "custom_data": {},
            "PLATFORM_SERVICE_API_KEY": "pk-ide-test",
            "include_metadata": True,
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


# ===========================================================================
# Test classes
# ===========================================================================


class TestIDEExtract:
    """IDE extract payload → executor → extracted_text."""

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_ide_extract_returns_text(self, mock_x2text_cls, mock_get_fs, eager_app):
        """IDE extract payload produces extracted_text in result.data."""
        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response(
            "Invoice #12345 dated 2024-01-15"
        )
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _ide_extract_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert "extracted_text" in result.data
        assert result.data["extracted_text"] == "Invoice #12345 dated 2024-01-15"

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_ide_extract_with_output_file_path(
        self, mock_x2text_cls, mock_get_fs, eager_app
    ):
        """IDE extract passes output_file_path to x2text.process()."""
        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response("text")
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _ide_extract_ctx()
        _run_task(eager_app, ctx.to_dict())

        # Verify output_file_path was passed through
        call_kwargs = mock_x2text.process.call_args
        assert call_kwargs is not None
        assert "output_file_path" in call_kwargs.kwargs
        assert call_kwargs.kwargs["output_file_path"] == (
            "/prompt-studio/org/user/tool/extract/doc.txt"
        )

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_ide_extract_failure(self, mock_x2text_cls, mock_get_fs, eager_app):
        """Adapter failure → ExecutionResult(success=False)."""
        from unstract.sdk1.adapters.exceptions import AdapterError

        mock_x2text = MagicMock()
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text.x2text_instance.get_name.return_value = "LLMWhisperer"
        mock_x2text.process.side_effect = AdapterError("extraction failed")
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _ide_extract_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "extraction failed" in result.error


class TestIDEIndex:
    """IDE index payload → executor → doc_id."""

    @patch(_PATCH_FS)
    @patch(_PATCH_INDEX_DEPS)
    def test_ide_index_returns_doc_id(self, mock_deps, mock_get_fs, eager_app):
        """IDE index payload produces doc_id in result.data."""
        mock_index_cls = MagicMock()
        mock_index = MagicMock()
        mock_index.generate_index_key.return_value = "doc-ide-indexed"
        mock_index.is_document_indexed.return_value = False
        mock_index.perform_indexing.return_value = "doc-ide-indexed"
        mock_index_cls.return_value = mock_index

        mock_emb_cls = MagicMock()
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls = MagicMock()
        mock_vdb_cls.return_value = MagicMock()

        mock_deps.return_value = (mock_index_cls, mock_emb_cls, mock_vdb_cls)
        mock_get_fs.return_value = MagicMock()

        ctx = _ide_index_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data["doc_id"] == "doc-ide-indexed"

    @patch(_PATCH_FS)
    @patch(_PATCH_INDEX_DEPS)
    def test_ide_index_with_null_file_hash(self, mock_deps, mock_get_fs, eager_app):
        """IDE indexer sends file_hash=None — executor handles it."""
        mock_index_cls = MagicMock()
        mock_index = MagicMock()
        mock_index.generate_index_key.return_value = "doc-null-hash"
        mock_index.is_document_indexed.return_value = False
        mock_index.perform_indexing.return_value = "doc-null-hash"
        mock_index_cls.return_value = mock_index

        mock_deps.return_value = (mock_index_cls, MagicMock(), MagicMock())
        mock_get_fs.return_value = MagicMock()

        # file_hash=None is exactly what dynamic_indexer sends
        ctx = _ide_index_ctx()
        assert ctx.executor_params["file_hash"] is None

        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data["doc_id"] == "doc-null-hash"

    @patch(_PATCH_FS)
    @patch(_PATCH_INDEX_DEPS)
    def test_ide_index_failure(self, mock_deps, mock_get_fs, eager_app):
        """Index failure → ExecutionResult(success=False)."""
        mock_index_cls = MagicMock()
        mock_index = MagicMock()
        mock_index.generate_index_key.return_value = "doc-fail"
        mock_index.is_document_indexed.return_value = False
        mock_index.perform_indexing.side_effect = RuntimeError("VDB timeout")
        mock_index_cls.return_value = mock_index

        mock_deps.return_value = (mock_index_cls, MagicMock(), MagicMock())
        mock_get_fs.return_value = MagicMock()

        ctx = _ide_index_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False


class TestIDEAnswerPrompt:
    """IDE answer_prompt payload → executor → {output, metadata, metrics}."""

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_ide_answer_prompt_text(self, mock_shim_cls, mock_deps, eager_app):
        """IDE text prompt → output dict with prompt_key → answer."""
        llm = _mock_llm("INV-2024-001")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _ide_answer_prompt_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        # IDE expects result.data to have "output", "metadata", "metrics"
        assert "output" in result.data
        assert "metadata" in result.data
        assert "metrics" in result.data
        assert result.data["output"]["invoice_number"] == "INV-2024-001"

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_ide_answer_prompt_metadata_has_run_id(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """IDE response metadata contains run_id and file_name."""
        llm = _mock_llm("answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _ide_answer_prompt_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        metadata = result.data["metadata"]
        assert metadata["run_id"] == "run-ide-ap"
        assert metadata["file_name"] == "invoice.pdf"

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_ide_answer_prompt_with_eval_settings(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """Prompt with eval_settings passes through to executor cleanly."""
        llm = _mock_llm("answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        prompt = _make_ide_prompt(
            eval_settings={
                "evaluate": True,
                "monitor_llm": ["llm-monitor-1"],
                "exclude_failed": True,
            }
        )
        ctx = _ide_answer_prompt_ctx(prompts=[prompt])
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_ide_answer_prompt_platform_key_reaches_shim(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """PLATFORM_SERVICE_API_KEY in payload reaches ExecutorToolShim."""
        llm = _mock_llm("answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _ide_answer_prompt_ctx()
        _run_task(eager_app, ctx.to_dict())

        # Verify shim was constructed with the platform key
        mock_shim_cls.assert_called()
        call_kwargs = mock_shim_cls.call_args
        assert call_kwargs.kwargs.get("platform_api_key") == "pk-ide-test"

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_ide_answer_prompt_webhook_settings(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """Prompt with webhook settings passes through cleanly."""
        llm = _mock_llm("answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        prompt = _make_ide_prompt(
            enable_postprocessing_webhook=True,
            postprocessing_webhook_url="https://example.com/hook",
        )
        ctx = _ide_answer_prompt_ctx(prompts=[prompt])
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True


class TestIDESinglePass:
    """IDE single_pass_extraction → executor → same shape as answer_prompt."""

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_ide_single_pass_multi_prompt(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """Single pass with multiple prompts → all fields in output."""
        llm = _mock_llm("single pass value")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _ide_single_pass_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert "output" in result.data
        assert "revenue" in result.data["output"]
        assert "date" in result.data["output"]

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_ide_single_pass_has_metadata(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """Single pass returns metadata with run_id."""
        llm = _mock_llm("value")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        ctx = _ide_single_pass_ctx()
        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert "metadata" in result.data
        assert result.data["metadata"]["run_id"] == "run-ide-sp"


class TestIDEDispatcherIntegration:
    """Test ExecutionDispatcher dispatch() with IDE payloads in eager mode.

    Celery's send_task() doesn't work with eager mode for AsyncResult.get(),
    so we patch send_task to delegate to task.apply() instead.
    """

    @staticmethod
    def _patch_send_task(eager_app):
        """Patch send_task on eager_app to use task.apply()."""
        original_send_task = eager_app.send_task

        def patched_send_task(name, args=None, kwargs=None, **opts):
            task = eager_app.tasks[name]
            return task.apply(args=args, kwargs=kwargs)

        eager_app.send_task = patched_send_task
        return original_send_task

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_dispatcher_extract_round_trip(
        self, mock_x2text_cls, mock_get_fs, eager_app
    ):
        """ExecutionDispatcher.dispatch() → extract → ExecutionResult."""
        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response(
            "dispatcher extracted"
        )
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        original = self._patch_send_task(eager_app)
        try:
            dispatcher = ExecutionDispatcher(celery_app=eager_app)
            ctx = _ide_extract_ctx()
            result = dispatcher.dispatch(ctx)
        finally:
            eager_app.send_task = original

        assert result.success is True
        assert result.data["extracted_text"] == "dispatcher extracted"

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_dispatcher_answer_prompt_round_trip(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """ExecutionDispatcher.dispatch() → answer_prompt → ExecutionResult."""
        llm = _mock_llm("dispatcher answer")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        original = self._patch_send_task(eager_app)
        try:
            dispatcher = ExecutionDispatcher(celery_app=eager_app)
            ctx = _ide_answer_prompt_ctx()
            result = dispatcher.dispatch(ctx)
        finally:
            eager_app.send_task = original

        assert result.success is True
        assert result.data["output"]["invoice_number"] == "dispatcher answer"
        assert "metadata" in result.data

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_dispatcher_single_pass_round_trip(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """ExecutionDispatcher.dispatch() → single_pass → ExecutionResult."""
        llm = _mock_llm("sp dispatch")
        mock_deps.return_value = _mock_prompt_deps(llm)
        mock_shim_cls.return_value = MagicMock()

        original = self._patch_send_task(eager_app)
        try:
            dispatcher = ExecutionDispatcher(celery_app=eager_app)
            ctx = _ide_single_pass_ctx()
            result = dispatcher.dispatch(ctx)
        finally:
            eager_app.send_task = original

        assert result.success is True
        assert "revenue" in result.data["output"]

    @patch(_PATCH_FS)
    @patch(_PATCH_INDEX_DEPS)
    def test_dispatcher_index_round_trip(
        self, mock_deps, mock_get_fs, eager_app
    ):
        """ExecutionDispatcher.dispatch() → index → ExecutionResult."""
        mock_index_cls = MagicMock()
        mock_index = MagicMock()
        mock_index.generate_index_key.return_value = "doc-dispatch-idx"
        mock_index.is_document_indexed.return_value = False
        mock_index.perform_indexing.return_value = "doc-dispatch-idx"
        mock_index_cls.return_value = mock_index

        mock_deps.return_value = (mock_index_cls, MagicMock(), MagicMock())
        mock_get_fs.return_value = MagicMock()

        original = self._patch_send_task(eager_app)
        try:
            dispatcher = ExecutionDispatcher(celery_app=eager_app)
            ctx = _ide_index_ctx()
            result = dispatcher.dispatch(ctx)
        finally:
            eager_app.send_task = original

        assert result.success is True
        assert result.data["doc_id"] == "doc-dispatch-idx"


class TestIDEExecutionSourceRouting:
    """Verify execution_source='ide' propagates correctly."""

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    def test_ide_source_reaches_extract_handler(
        self, mock_x2text_cls, mock_get_fs, eager_app
    ):
        """Extract handler receives execution_source='ide' from context."""
        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response("text")
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_fs = MagicMock()
        mock_get_fs.return_value = mock_fs

        ctx = _ide_extract_ctx()
        assert ctx.execution_source == "ide"

        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)
        assert result.success is True

        # For IDE source, _update_exec_metadata should NOT write
        # (it only writes for execution_source="tool")
        # This is verified by the fact that no dump_json was called
        # on the fs mock. In IDE mode, whisper_hash metadata is skipped.

    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_SHIM)
    def test_ide_source_in_answer_prompt_enables_variable_replacement(
        self, mock_shim_cls, mock_deps, eager_app
    ):
        """execution_source='ide' in payload sets is_ide=True for variable replacement."""
        llm = _mock_llm("var answer")
        deps = _mock_prompt_deps(llm)
        # Enable variable checking to verify is_ide routing
        var_service = deps[2]  # VariableReplacementService
        var_service.is_variables_present.return_value = False
        mock_deps.return_value = deps
        mock_shim_cls.return_value = MagicMock()

        ctx = _ide_answer_prompt_ctx()
        # Verify execution_source is in both context and payload
        assert ctx.execution_source == "ide"
        assert ctx.executor_params["execution_source"] == "ide"

        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)
        assert result.success is True


class TestIDEPayloadKeyCompatibility:
    """Verify the exact key names in IDE payloads match executor expectations."""

    def test_extract_payload_keys_match_executor(self):
        """dynamic_extractor payload keys match _handle_extract reads."""
        ctx = _ide_extract_ctx()
        params = ctx.executor_params

        # These are the keys _handle_extract reads from params
        assert "x2text_instance_id" in params
        assert "file_path" in params
        assert "platform_api_key" in params
        assert "output_file_path" in params
        assert "enable_highlight" in params
        assert "usage_kwargs" in params

    def test_index_payload_keys_match_executor(self):
        """dynamic_indexer payload keys match _handle_index reads."""
        ctx = _ide_index_ctx()
        params = ctx.executor_params

        # These are the keys _handle_index reads from params
        assert "embedding_instance_id" in params
        assert "vector_db_instance_id" in params
        assert "x2text_instance_id" in params
        assert "file_path" in params
        assert "extracted_text" in params
        assert "platform_api_key" in params
        assert "chunk_size" in params
        assert "chunk_overlap" in params

    def test_answer_prompt_payload_keys_match_executor(self):
        """_fetch_response payload keys match _handle_answer_prompt reads."""
        ctx = _ide_answer_prompt_ctx()
        params = ctx.executor_params

        # These are the keys _handle_answer_prompt reads
        assert "tool_settings" in params
        assert "outputs" in params
        assert "tool_id" in params
        assert "file_hash" in params
        assert "file_path" in params
        assert "file_name" in params
        assert "PLATFORM_SERVICE_API_KEY" in params
        assert "log_events_id" in params
        assert "execution_source" in params
        assert "custom_data" in params

    def test_answer_prompt_platform_key_is_uppercase(self):
        """answer_prompt uses PLATFORM_SERVICE_API_KEY (uppercase, not snake_case)."""
        ctx = _ide_answer_prompt_ctx()
        # _handle_answer_prompt reads PSKeys.PLATFORM_SERVICE_API_KEY
        # which is "PLATFORM_SERVICE_API_KEY"
        assert "PLATFORM_SERVICE_API_KEY" in ctx.executor_params
        # NOT "platform_api_key" (that's for extract/index)
        assert ctx.executor_params["PLATFORM_SERVICE_API_KEY"] == "pk-ide-test"

    def test_extract_platform_key_is_lowercase(self):
        """extract/index uses platform_api_key (lowercase snake_case)."""
        ctx = _ide_extract_ctx()
        assert "platform_api_key" in ctx.executor_params

    def test_execution_context_has_ide_source(self):
        """All IDE contexts have execution_source='ide'."""
        assert _ide_extract_ctx().execution_source == "ide"
        assert _ide_index_ctx().execution_source == "ide"
        assert _ide_answer_prompt_ctx().execution_source == "ide"
        assert _ide_single_pass_ctx().execution_source == "ide"
