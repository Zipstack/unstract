"""Phase 2C — LegacyExecutor._handle_index tests.

Verifies:
1. Happy path: indexing returns success with doc_id
2. Chunk size 0: skips indexing, still returns doc_id
3. Missing required params → failure result
4. Reindex flag: passes reindex through to Index
5. VectorDB.close() always called (even on error)
6. Indexing error → LegacyExecutorError → failure result
7. Orchestrator integration: index returns success (mocked)
8. Celery eager-mode: full task chain returns indexing result
9. Index class: generate_index_key called with correct DTOs
10. EmbeddingCompat and VectorDB created with correct params

Heavy SDK1 dependencies (llama_index, qdrant) are lazily imported
via ``LegacyExecutor._get_indexing_deps()``. We mock that method
to avoid protobuf conflicts in the test environment.
"""

from unittest.mock import MagicMock, patch

import pytest

from executor.executors.constants import IndexingConstants as IKeys
from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.orchestrator import ExecutionOrchestrator
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


@pytest.fixture(autouse=True)
def _clean_registry():
    ExecutorRegistry.clear()
    yield
    ExecutorRegistry.clear()


def _register_legacy():
    from executor.executors.legacy_executor import LegacyExecutor  # noqa: F401

    ExecutorRegistry.register(LegacyExecutor)


def _make_index_context(**overrides):
    defaults = {
        "executor_name": "legacy",
        "operation": "index",
        "run_id": "run-2c-001",
        "execution_source": "tool",
        "organization_id": "org-test",
        "request_id": "req-2c-001",
        "executor_params": {
            "embedding_instance_id": "emb-001",
            "vector_db_instance_id": "vdb-001",
            "x2text_instance_id": "x2t-001",
            "file_path": "/data/test.pdf",
            "file_hash": "abc123",
            "extracted_text": "Hello world",
            "platform_api_key": "sk-test",
            "chunk_size": 512,
            "chunk_overlap": 128,
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


_PATCH_FS = "executor.executors.legacy_executor.FileUtils.get_fs_instance"
_PATCH_DEPS = (
    "executor.executors.legacy_executor.LegacyExecutor._get_indexing_deps"
)


@pytest.fixture
def mock_indexing_deps():
    """Mock the heavy indexing dependencies via _get_indexing_deps()."""
    mock_index_cls = MagicMock()
    mock_emb_cls = MagicMock()
    mock_vdb_cls = MagicMock()

    with patch(_PATCH_DEPS, return_value=(mock_index_cls, mock_emb_cls, mock_vdb_cls)):
        yield mock_index_cls, mock_emb_cls, mock_vdb_cls


def _setup_mock_index(mock_index_cls, doc_id="doc-hash-123"):
    """Configure a mock Index instance."""
    mock_index = MagicMock()
    mock_index.generate_index_key.return_value = doc_id
    mock_index.is_document_indexed.return_value = False
    mock_index.perform_indexing.return_value = doc_id
    mock_index_cls.return_value = mock_index
    return mock_index


# --- 1. Happy path ---


class TestHappyPath:
    @patch(_PATCH_FS)
    def test_index_returns_success_with_doc_id(
        self, mock_get_fs, mock_indexing_deps
    ):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        _setup_mock_index(mock_index_cls, "doc-hash-123")
        mock_emb_cls.return_value = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb_cls.return_value = mock_vdb
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context()
        result = executor.execute(ctx)

        assert result.success is True
        assert result.data[IKeys.DOC_ID] == "doc-hash-123"
        mock_vdb.close.assert_called_once()


# --- 2. Chunk size 0: skips indexing ---


class TestChunkSizeZero:
    @patch(
        "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
        return_value="doc-zero-chunk",
    )
    @patch(_PATCH_FS)
    def test_chunk_size_zero_skips_indexing(self, mock_get_fs, mock_gen_key):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context(
            executor_params={
                "embedding_instance_id": "emb-001",
                "vector_db_instance_id": "vdb-001",
                "x2text_instance_id": "x2t-001",
                "file_path": "/data/test.pdf",
                "file_hash": "abc123",
                "extracted_text": "text",
                "platform_api_key": "sk-test",
                "chunk_size": 0,
                "chunk_overlap": 0,
            }
        )
        result = executor.execute(ctx)

        assert result.success is True
        assert result.data[IKeys.DOC_ID] == "doc-zero-chunk"
        mock_gen_key.assert_called_once()


# --- 3. Missing required params ---


class TestMissingParams:
    def test_missing_embedding_instance_id(self):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")
        ctx = _make_index_context(
            executor_params={
                "vector_db_instance_id": "vdb-001",
                "x2text_instance_id": "x2t-001",
                "file_path": "/data/test.pdf",
                "platform_api_key": "sk-test",
            }
        )
        result = executor.execute(ctx)
        assert result.success is False
        assert "embedding_instance_id" in result.error

    def test_missing_multiple_params(self):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")
        ctx = _make_index_context(
            executor_params={"platform_api_key": "sk-test"}
        )
        result = executor.execute(ctx)
        assert result.success is False
        assert "embedding_instance_id" in result.error
        assert "vector_db_instance_id" in result.error
        assert "x2text_instance_id" in result.error
        assert "file_path" in result.error


# --- 4. Reindex flag ---


class TestReindex:
    @patch(_PATCH_FS)
    def test_reindex_passed_through(self, mock_get_fs, mock_indexing_deps):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        _setup_mock_index(mock_index_cls, "doc-reindex")
        mock_index_cls.return_value.is_document_indexed.return_value = True
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls.return_value = MagicMock()
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context(
            executor_params={
                "embedding_instance_id": "emb-001",
                "vector_db_instance_id": "vdb-001",
                "x2text_instance_id": "x2t-001",
                "file_path": "/data/test.pdf",
                "file_hash": "abc123",
                "extracted_text": "text",
                "platform_api_key": "sk-test",
                "chunk_size": 512,
                "chunk_overlap": 128,
                "reindex": True,
            }
        )
        result = executor.execute(ctx)

        assert result.success is True
        init_call = mock_index_cls.call_args
        assert init_call.kwargs["processing_options"].reindex is True


# --- 5. VectorDB.close() always called ---


class TestVectorDBClose:
    @patch(_PATCH_FS)
    def test_vectordb_closed_on_success(self, mock_get_fs, mock_indexing_deps):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        _setup_mock_index(mock_index_cls)
        mock_emb_cls.return_value = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb_cls.return_value = mock_vdb
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context()
        executor.execute(ctx)
        mock_vdb.close.assert_called_once()

    @patch(_PATCH_FS)
    def test_vectordb_closed_on_error(self, mock_get_fs, mock_indexing_deps):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_index = _setup_mock_index(mock_index_cls)
        mock_index.is_document_indexed.side_effect = RuntimeError("boom")
        mock_emb_cls.return_value = MagicMock()
        mock_vdb = MagicMock()
        mock_vdb_cls.return_value = mock_vdb
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context()
        result = executor.execute(ctx)

        assert result.success is False
        mock_vdb.close.assert_called_once()


# --- 6. Indexing error → failure result ---


class TestIndexingError:
    @patch(_PATCH_FS)
    def test_indexing_error_returns_failure(
        self, mock_get_fs, mock_indexing_deps
    ):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_index = _setup_mock_index(mock_index_cls, "doc-err")
        mock_index.perform_indexing.side_effect = RuntimeError(
            "vector DB unavailable"
        )
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls.return_value = MagicMock()
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context()
        result = executor.execute(ctx)

        assert result.success is False
        assert "indexing" in result.error.lower()
        assert "vector DB unavailable" in result.error


# --- 7. Orchestrator integration ---


class TestOrchestratorIntegration:
    @patch(_PATCH_FS)
    def test_orchestrator_index_returns_success(
        self, mock_get_fs, mock_indexing_deps
    ):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()
        orchestrator = ExecutionOrchestrator()

        _setup_mock_index(mock_index_cls, "doc-orch")
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls.return_value = MagicMock()
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context()
        result = orchestrator.execute(ctx)

        assert result.success is True
        assert result.data[IKeys.DOC_ID] == "doc-orch"


# --- 8. Celery eager-mode ---


@pytest.fixture
def eager_app():
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


class TestCeleryEager:
    @patch(_PATCH_FS)
    def test_eager_index_returns_success(
        self, mock_get_fs, mock_indexing_deps, eager_app
    ):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()

        _setup_mock_index(mock_index_cls, "doc-celery")
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls.return_value = MagicMock()
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context()
        task = eager_app.tasks["execute_extraction"]
        result_dict = task.apply(args=[ctx.to_dict()]).get()
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data[IKeys.DOC_ID] == "doc-celery"


# --- 9. Index class receives correct DTOs ---


class TestIndexDTOs:
    @patch(_PATCH_FS)
    def test_index_created_with_correct_dtos(
        self, mock_get_fs, mock_indexing_deps
    ):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        _setup_mock_index(mock_index_cls, "doc-dto")
        mock_emb_cls.return_value = MagicMock()
        mock_vdb_cls.return_value = MagicMock()
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context(
            executor_params={
                "embedding_instance_id": "emb-dto",
                "vector_db_instance_id": "vdb-dto",
                "x2text_instance_id": "x2t-dto",
                "file_path": "/data/doc.pdf",
                "file_hash": "hash-dto",
                "extracted_text": "text",
                "platform_api_key": "sk-test",
                "chunk_size": 256,
                "chunk_overlap": 64,
                "tool_id": "tool-dto",
                "tags": ["tag1"],
            }
        )
        executor.execute(ctx)

        init_kwargs = mock_index_cls.call_args.kwargs
        ids = init_kwargs["instance_identifiers"]
        assert ids.embedding_instance_id == "emb-dto"
        assert ids.vector_db_instance_id == "vdb-dto"
        assert ids.x2text_instance_id == "x2t-dto"
        assert ids.tool_id == "tool-dto"
        assert ids.tags == ["tag1"]

        chunking = init_kwargs["chunking_config"]
        assert chunking.chunk_size == 256
        assert chunking.chunk_overlap == 64

        gen_call = mock_index_cls.return_value.generate_index_key.call_args
        fi = gen_call.kwargs["file_info"]
        assert fi.file_path == "/data/doc.pdf"
        assert fi.file_hash == "hash-dto"


# --- 10. EmbeddingCompat and VectorDB created with correct params ---


class TestAdapterCreation:
    @patch(_PATCH_FS)
    def test_embedding_and_vectordb_params(
        self, mock_get_fs, mock_indexing_deps
    ):
        mock_index_cls, mock_emb_cls, mock_vdb_cls = mock_indexing_deps
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        _setup_mock_index(mock_index_cls, "doc-adapt")
        mock_emb = MagicMock()
        mock_emb_cls.return_value = mock_emb
        mock_vdb = MagicMock()
        mock_vdb_cls.return_value = mock_vdb
        mock_get_fs.return_value = MagicMock()

        ctx = _make_index_context(
            executor_params={
                "embedding_instance_id": "emb-check",
                "vector_db_instance_id": "vdb-check",
                "x2text_instance_id": "x2t-001",
                "file_path": "/data/test.pdf",
                "file_hash": "abc",
                "extracted_text": "text",
                "platform_api_key": "sk-test",
                "chunk_size": 512,
                "chunk_overlap": 128,
                "usage_kwargs": {"org": "test-org"},
            }
        )
        executor.execute(ctx)

        emb_call = mock_emb_cls.call_args
        assert emb_call.kwargs["adapter_instance_id"] == "emb-check"
        assert emb_call.kwargs["kwargs"] == {"org": "test-org"}

        vdb_call = mock_vdb_cls.call_args
        assert vdb_call.kwargs["adapter_instance_id"] == "vdb-check"
        assert vdb_call.kwargs["embedding"] is mock_emb
