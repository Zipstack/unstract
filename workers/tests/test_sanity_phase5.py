"""Phase 5-SANITY — Integration tests for the multi-hop elimination.

Phase 5 eliminates idle backend worker slots by:
  - Adding ``dispatch_with_callback`` (fire-and-forget with link/link_error)
  - Adding compound operations: ``ide_index``, ``structure_pipeline``
  - Rewiring structure_tool_task to single ``structure_pipeline`` dispatch

These tests push payloads through the full Celery eager-mode chain and
verify the results match what callers (views / structure_tool_task) expect.
"""

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


def _mock_llm(answer="pipeline answer"):
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
    index_instance.generate_index_key.return_value = "doc-key-1"
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


def _mock_process_response(text="extracted text"):
    """Build a mock TextExtractionResult."""
    from unstract.sdk1.adapters.x2text.dto import (
        TextExtractionMetadata,
        TextExtractionResult,
    )

    metadata = TextExtractionMetadata(whisper_hash="test-hash")
    return TextExtractionResult(
        extracted_text=text,
        extraction_metadata=metadata,
    )


def _make_output(name="field_a", prompt="What is the revenue?", **overrides):
    """Build an output dict for answer_prompt payloads."""
    d = {
        PSKeys.NAME: name,
        PSKeys.PROMPT: prompt,
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
    }
    d.update(overrides)
    return d


# ---------------------------------------------------------------------------
# 5A: dispatch_with_callback
# ---------------------------------------------------------------------------


class TestDispatchWithCallback:
    """Verify dispatch_with_callback passes link/link_error to send_task."""

    def test_callback_kwargs_passed(self):
        mock_app = MagicMock()
        mock_app.send_task.return_value = MagicMock(id="task-123")
        dispatcher = ExecutionDispatcher(celery_app=mock_app)

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="answer_prompt",
            run_id="run-cb-1",
            execution_source="ide",
        )
        on_success = MagicMock(name="success_sig")
        on_error = MagicMock(name="error_sig")

        result = dispatcher.dispatch_with_callback(
            ctx,
            on_success=on_success,
            on_error=on_error,
            task_id="pre-generated-id",
        )

        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs.kwargs["link"] is on_success
        assert call_kwargs.kwargs["link_error"] is on_error
        assert call_kwargs.kwargs["task_id"] == "pre-generated-id"
        assert result.id == "task-123"

    def test_no_callbacks_omits_link_kwargs(self):
        mock_app = MagicMock()
        mock_app.send_task.return_value = MagicMock(id="task-456")
        dispatcher = ExecutionDispatcher(celery_app=mock_app)

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="run-cb-2",
            execution_source="tool",
        )
        dispatcher.dispatch_with_callback(ctx)

        call_kwargs = mock_app.send_task.call_args
        assert "link" not in call_kwargs.kwargs
        assert "link_error" not in call_kwargs.kwargs

    def test_no_app_raises(self):
        dispatcher = ExecutionDispatcher(celery_app=None)
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="run-cb-3",
            execution_source="tool",
        )
        with pytest.raises(ValueError, match="No Celery app"):
            dispatcher.dispatch_with_callback(ctx)


# ---------------------------------------------------------------------------
# 5C: ide_index compound operation through eager chain
# ---------------------------------------------------------------------------


class TestIdeIndexEagerChain:
    """ide_index: extract + index in a single executor invocation."""

    @patch(_PATCH_INDEX_DEPS)
    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    @patch(_PATCH_SHIM)
    def test_ide_index_success(
        self,
        MockShim,
        MockX2Text,
        mock_fs,
        mock_index_deps,
        eager_app,
    ):
        """Full ide_index through eager chain returns doc_id."""
        # Mock extract
        x2t_instance = MagicMock()
        x2t_instance.process.return_value = _mock_process_response(
            "IDE extracted text"
        )
        MockX2Text.return_value = x2t_instance

        fs = MagicMock()
        fs.exists.return_value = False
        mock_fs.return_value = fs

        # Mock index
        index_inst = MagicMock()
        index_inst.index.return_value = "idx-doc-1"
        index_inst.generate_index_key.return_value = "idx-key-1"
        mock_index_deps.return_value = (
            MagicMock(return_value=index_inst),  # Index
            MagicMock(),  # EmbeddingCompat
            MagicMock(),  # VectorDB
        )

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="ide_index",
            run_id="run-ide-idx",
            execution_source="ide",
            organization_id="org-test",
            executor_params={
                "extract_params": {
                    "x2text_instance_id": "x2t-1",
                    "file_path": "/data/doc.pdf",
                    "enable_highlight": False,
                    "output_file_path": "/data/extract/doc.txt",
                    "platform_api_key": "pk-test",
                    "usage_kwargs": {},
                },
                "index_params": {
                    "tool_id": "tool-1",
                    "embedding_instance_id": "emb-1",
                    "vector_db_instance_id": "vdb-1",
                    "x2text_instance_id": "x2t-1",
                    "file_path": "/data/extract/doc.txt",
                    "file_hash": None,
                    "chunk_overlap": 64,
                    "chunk_size": 512,
                    "reindex": True,
                    "enable_highlight": False,
                    "usage_kwargs": {},
                    "run_id": "run-ide-idx",
                    "execution_source": "ide",
                    "platform_api_key": "pk-test",
                },
            },
        )

        result_dict = _run_task(eager_app, ctx.to_dict())

        result = ExecutionResult.from_dict(result_dict)
        assert result.success
        assert "doc_id" in result.data

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    @patch(_PATCH_SHIM)
    def test_ide_index_extract_failure(
        self,
        MockShim,
        MockX2Text,
        mock_fs,
        eager_app,
    ):
        """ide_index returns failure if extract fails."""
        x2t_instance = MagicMock()
        x2t_instance.process.side_effect = Exception("X2Text unavailable")
        MockX2Text.return_value = x2t_instance

        fs = MagicMock()
        fs.exists.return_value = False
        mock_fs.return_value = fs

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="ide_index",
            run_id="run-ide-fail",
            execution_source="ide",
            executor_params={
                "extract_params": {
                    "x2text_instance_id": "x2t-1",
                    "file_path": "/data/doc.pdf",
                    "enable_highlight": False,
                    "platform_api_key": "pk-test",
                    "usage_kwargs": {},
                },
                "index_params": {
                    "tool_id": "tool-1",
                    "embedding_instance_id": "emb-1",
                    "vector_db_instance_id": "vdb-1",
                    "x2text_instance_id": "x2t-1",
                    "file_path": "/data/extract/doc.txt",
                    "file_hash": None,
                    "chunk_overlap": 64,
                    "chunk_size": 512,
                    "reindex": True,
                    "enable_highlight": False,
                    "usage_kwargs": {},
                    "run_id": "run-ide-fail",
                    "execution_source": "ide",
                    "platform_api_key": "pk-test",
                },
            },
        )

        result_dict = _run_task(eager_app, ctx.to_dict())
        result = ExecutionResult.from_dict(result_dict)
        assert not result.success
        assert "X2Text" in result.error


# ---------------------------------------------------------------------------
# 5D: structure_pipeline compound operation through eager chain
# ---------------------------------------------------------------------------


class TestStructurePipelineEagerChain:
    """structure_pipeline: full extract→index→answer through eager chain."""

    @patch(_PATCH_INDEX_UTILS, return_value="doc-id-pipeline")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_INDEX_DEPS)
    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    @patch(_PATCH_SHIM)
    def test_structure_pipeline_normal(
        self,
        MockShim,
        MockX2Text,
        mock_fs,
        mock_index_deps,
        mock_prompt_deps,
        _mock_idx_utils,
        eager_app,
    ):
        """Normal pipeline: extract → index → answer_prompt."""
        # Mock extract
        x2t_instance = MagicMock()
        x2t_instance.process.return_value = _mock_process_response("Revenue is $1M")
        MockX2Text.return_value = x2t_instance

        fs = MagicMock()
        fs.exists.return_value = False
        mock_fs.return_value = fs

        # Mock index
        index_inst = MagicMock()
        index_inst.index.return_value = "idx-doc-1"
        index_inst.generate_index_key.return_value = "idx-key-1"
        mock_index_deps.return_value = (
            MagicMock(return_value=index_inst),
            MagicMock(),
            MagicMock(),
        )

        # Mock prompt deps
        mock_prompt_deps.return_value = _mock_prompt_deps()

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="structure_pipeline",
            run_id="run-sp-1",
            execution_source="tool",
            organization_id="org-test",
            executor_params={
                "extract_params": {
                    "x2text_instance_id": "x2t-1",
                    "file_path": "/data/test.pdf",
                    "enable_highlight": False,
                    "output_file_path": "/data/exec/EXTRACT",
                    "platform_api_key": "pk-test",
                    "usage_kwargs": {},
                },
                "index_template": {
                    "tool_id": "tool-1",
                    "file_hash": "hash123",
                    "is_highlight_enabled": False,
                    "platform_api_key": "pk-test",
                    "extracted_file_path": "/data/exec/EXTRACT",
                },
                "answer_params": {
                    "run_id": "run-sp-1",
                    "execution_id": "exec-1",
                    "tool_settings": {
                        "vector-db": "vdb-1",
                        "embedding": "emb-1",
                        "x2text_adapter": "x2t-1",
                        "llm": "llm-1",
                        "enable_challenge": False,
                        "challenge_llm": "",
                        "enable_single_pass_extraction": False,
                        "summarize_as_source": False,
                        "enable_highlight": False,
                    },
                    "outputs": [_make_output()],
                    "tool_id": "tool-1",
                    "file_hash": "hash123",
                    "file_name": "test.pdf",
                    "file_path": "/data/exec/EXTRACT",
                    "execution_source": "tool",
                    "PLATFORM_SERVICE_API_KEY": "pk-test",
                },
                "pipeline_options": {
                    "skip_extraction_and_indexing": False,
                    "is_summarization_enabled": False,
                    "is_single_pass_enabled": False,
                    "input_file_path": "/data/test.pdf",
                    "source_file_name": "test.pdf",
                },
                "summarize_params": None,
            },
        )

        result_dict = _run_task(eager_app, ctx.to_dict())

        result = ExecutionResult.from_dict(result_dict)
        assert result.success
        assert "output" in result.data
        assert "metadata" in result.data
        # source_file_name injected into metadata
        assert result.data["metadata"]["file_name"] == "test.pdf"

    @patch(_PATCH_INDEX_UTILS, return_value="doc-id-sp")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    @patch(_PATCH_SHIM)
    def test_structure_pipeline_single_pass(
        self,
        MockShim,
        MockX2Text,
        mock_fs,
        mock_prompt_deps,
        _mock_idx_utils,
        eager_app,
    ):
        """Single pass: extract → single_pass_extraction (no index)."""
        x2t_instance = MagicMock()
        x2t_instance.process.return_value = _mock_process_response("Revenue data")
        MockX2Text.return_value = x2t_instance

        fs = MagicMock()
        fs.exists.return_value = False
        mock_fs.return_value = fs

        mock_prompt_deps.return_value = _mock_prompt_deps()

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="structure_pipeline",
            run_id="run-sp-sp",
            execution_source="tool",
            executor_params={
                "extract_params": {
                    "x2text_instance_id": "x2t-1",
                    "file_path": "/data/test.pdf",
                    "enable_highlight": False,
                    "output_file_path": "/data/exec/EXTRACT",
                    "platform_api_key": "pk-test",
                    "usage_kwargs": {},
                },
                "index_template": {},
                "answer_params": {
                    "run_id": "run-sp-sp",
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
                    "outputs": [_make_output()],
                    "tool_id": "tool-1",
                    "file_hash": "hash123",
                    "file_name": "test.pdf",
                    "file_path": "/data/exec/EXTRACT",
                    "execution_source": "tool",
                    "PLATFORM_SERVICE_API_KEY": "pk-test",
                },
                "pipeline_options": {
                    "skip_extraction_and_indexing": False,
                    "is_summarization_enabled": False,
                    "is_single_pass_enabled": True,
                    "input_file_path": "/data/test.pdf",
                    "source_file_name": "test.pdf",
                },
                "summarize_params": None,
            },
        )

        result_dict = _run_task(eager_app, ctx.to_dict())

        result = ExecutionResult.from_dict(result_dict)
        assert result.success
        assert "output" in result.data

    @patch(_PATCH_INDEX_UTILS, return_value="doc-id-skip")
    @patch(_PATCH_PROMPT_DEPS)
    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    @patch(_PATCH_SHIM)
    def test_structure_pipeline_skip_extraction(
        self,
        MockShim,
        MockX2Text,
        mock_fs,
        mock_prompt_deps,
        _mock_idx_utils,
        eager_app,
    ):
        """Smart table: skip extraction, go straight to answer_prompt."""
        fs = MagicMock()
        fs.exists.return_value = False
        mock_fs.return_value = fs

        mock_prompt_deps.return_value = _mock_prompt_deps()

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="structure_pipeline",
            run_id="run-sp-skip",
            execution_source="tool",
            executor_params={
                "extract_params": {},
                "index_template": {},
                "answer_params": {
                    "run_id": "run-sp-skip",
                    "tool_settings": {
                        "vector-db": "vdb-1",
                        "embedding": "emb-1",
                        "x2text_adapter": "x2t-1",
                        "llm": "llm-1",
                        "enable_challenge": False,
                        "challenge_llm": "",
                        "enable_single_pass_extraction": False,
                        "summarize_as_source": False,
                        "enable_highlight": False,
                    },
                    "outputs": [_make_output(prompt='{"key": "value"}')],
                    "tool_id": "tool-1",
                    "file_hash": "hash123",
                    "file_name": "test.xlsx",
                    "file_path": "/data/test.xlsx",
                    "execution_source": "tool",
                    "PLATFORM_SERVICE_API_KEY": "pk-test",
                },
                "pipeline_options": {
                    "skip_extraction_and_indexing": True,
                    "is_summarization_enabled": False,
                    "is_single_pass_enabled": False,
                    "input_file_path": "/data/test.xlsx",
                    "source_file_name": "test.xlsx",
                },
                "summarize_params": None,
            },
        )

        result_dict = _run_task(eager_app, ctx.to_dict())

        result = ExecutionResult.from_dict(result_dict)
        assert result.success
        # No extract was called (X2Text not mocked beyond fixture)
        MockX2Text.assert_not_called()

    @patch(_PATCH_FS)
    @patch(_PATCH_X2TEXT)
    @patch(_PATCH_SHIM)
    def test_structure_pipeline_extract_failure(
        self,
        MockShim,
        MockX2Text,
        mock_fs,
        eager_app,
    ):
        """Pipeline extract failure propagated as result failure."""
        x2t_instance = MagicMock()
        x2t_instance.process.side_effect = Exception("X2Text timeout")
        MockX2Text.return_value = x2t_instance

        fs = MagicMock()
        fs.exists.return_value = False
        mock_fs.return_value = fs

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="structure_pipeline",
            run_id="run-sp-fail",
            execution_source="tool",
            executor_params={
                "extract_params": {
                    "x2text_instance_id": "x2t-1",
                    "file_path": "/data/test.pdf",
                    "enable_highlight": False,
                    "platform_api_key": "pk-test",
                    "usage_kwargs": {},
                },
                "index_template": {},
                "answer_params": {},
                "pipeline_options": {
                    "skip_extraction_and_indexing": False,
                    "is_summarization_enabled": False,
                    "is_single_pass_enabled": False,
                    "input_file_path": "/data/test.pdf",
                    "source_file_name": "test.pdf",
                },
                "summarize_params": None,
            },
        )

        result_dict = _run_task(eager_app, ctx.to_dict())

        result = ExecutionResult.from_dict(result_dict)
        assert not result.success
        assert "X2Text" in result.error


# ---------------------------------------------------------------------------
# 5E: structure_tool_task single dispatch verification
# ---------------------------------------------------------------------------


class TestStructureToolSingleDispatch:
    """Verify structure_tool_task dispatches exactly once."""

    @patch(
        "executor.executor_tool_shim.ExecutorToolShim"
    )
    @patch(
        "file_processing.structure_tool_task._get_file_storage"
    )
    @patch(
        "file_processing.structure_tool_task._create_platform_helper"
    )
    @patch(
        "file_processing.structure_tool_task.ExecutionDispatcher"
    )
    def test_single_dispatch_normal(
        self,
        MockDispatcher,
        mock_create_ph,
        mock_get_fs,
        MockShim,
    ):
        """Normal path sends single structure_pipeline dispatch."""
        from file_processing.structure_tool_task import (
            _execute_structure_tool_impl,
        )

        fs = MagicMock()
        fs.exists.return_value = False
        mock_get_fs.return_value = fs

        ph = MagicMock()
        ph.get_prompt_studio_tool.return_value = {
            "tool_metadata": {
                "name": "Test",
                "is_agentic": False,
                "tool_id": "t1",
                "tool_settings": {
                    "vector-db": "v1",
                    "embedding": "e1",
                    "x2text_adapter": "x1",
                    "llm": "l1",
                },
                "outputs": [
                    {
                        "name": "f1",
                        "prompt": "What?",
                        "type": "text",
                        "active": True,
                        "chunk-size": 512,
                        "chunk-overlap": 64,
                        "llm": "l1",
                        "embedding": "e1",
                        "vector-db": "v1",
                        "x2text_adapter": "x1",
                    },
                ],
            },
        }
        mock_create_ph.return_value = ph

        dispatcher = MagicMock()
        MockDispatcher.return_value = dispatcher
        dispatcher.dispatch.return_value = ExecutionResult(
            success=True,
            data={"output": {"f1": "ans"}, "metadata": {}, "metrics": {}},
        )

        params = {
            "organization_id": "org-1",
            "workflow_id": "wf-1",
            "execution_id": "ex-1",
            "file_execution_id": "fex-1",
            "tool_instance_metadata": {"prompt_registry_id": "pr-1"},
            "platform_service_api_key": "pk-1",
            "input_file_path": "/data/test.pdf",
            "output_dir_path": "/output",
            "source_file_name": "test.pdf",
            "execution_data_dir": "/data/exec",
            "file_hash": "h1",
            "exec_metadata": {},
        }

        result = _execute_structure_tool_impl(params)

        assert result["success"] is True
        assert dispatcher.dispatch.call_count == 1
        ctx = dispatcher.dispatch.call_args[0][0]
        assert ctx.operation == "structure_pipeline"
        assert "extract_params" in ctx.executor_params
        assert "index_template" in ctx.executor_params
        assert "answer_params" in ctx.executor_params
        assert "pipeline_options" in ctx.executor_params


# ---------------------------------------------------------------------------
# Operation enum completeness
# ---------------------------------------------------------------------------


class TestOperationEnum:
    """Verify Phase 5 operations registered in enum."""

    def test_ide_index_operation(self):
        assert hasattr(Operation, "IDE_INDEX")
        assert Operation.IDE_INDEX.value == "ide_index"

    def test_structure_pipeline_operation(self):
        assert hasattr(Operation, "STRUCTURE_PIPELINE")
        assert Operation.STRUCTURE_PIPELINE.value == "structure_pipeline"


# ---------------------------------------------------------------------------
# Dispatcher modes
# ---------------------------------------------------------------------------


class TestDispatcherModes:
    """Verify all three dispatch modes work."""

    def test_dispatch_sync(self):
        """dispatch() calls send_task and .get()."""
        mock_app = MagicMock()
        async_result = MagicMock()
        async_result.get.return_value = ExecutionResult(
            success=True, data={"test": 1}
        ).to_dict()
        mock_app.send_task.return_value = async_result

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="r1",
            execution_source="tool",
        )
        result = dispatcher.dispatch(ctx, timeout=10)

        assert result.success
        mock_app.send_task.assert_called_once()
        async_result.get.assert_called_once()

    def test_dispatch_async(self):
        """dispatch_async() returns task_id without blocking."""
        mock_app = MagicMock()
        mock_app.send_task.return_value = MagicMock(id="async-id")

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="r2",
            execution_source="tool",
        )
        task_id = dispatcher.dispatch_async(ctx)

        assert task_id == "async-id"
        mock_app.send_task.assert_called_once()
