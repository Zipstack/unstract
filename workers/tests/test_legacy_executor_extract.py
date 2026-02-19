"""Phase 2B — LegacyExecutor._handle_extract tests.

Verifies:
1. Happy path: extraction returns success with extracted_text
2. With highlight (LLMWhisperer): enable_highlight passed through
3. Without highlight (non-Whisperer): enable_highlight NOT passed
4. AdapterError → failure result
5. Missing required params → failure result
6. Metadata update for tool source: ToolUtils.dump_json called
7. IDE source skips metadata writing
8. FileUtils routing: correct storage type for ide vs tool
9. Orchestrator integration: extract returns success (mocked)
10. Celery eager-mode: full task chain returns extraction result
11. LegacyExecutorError caught by execute() → failure result
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from executor.executors.constants import (
    ExecutionSource,
    FileStorageKeys,
    IndexingConstants as IKeys,
)
from executor.executors.exceptions import ExtractionError, LegacyExecutorError
from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.adapters.x2text.dto import (
    TextExtractionMetadata,
    TextExtractionResult,
)
from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.orchestrator import ExecutionOrchestrator
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure a clean executor registry for every test."""
    ExecutorRegistry.clear()
    yield
    ExecutorRegistry.clear()


def _register_legacy():
    from executor.executors.legacy_executor import LegacyExecutor  # noqa: F401

    ExecutorRegistry.register(LegacyExecutor)


def _make_context(**overrides):
    defaults = {
        "executor_name": "legacy",
        "operation": "extract",
        "run_id": "run-2b-001",
        "execution_source": "tool",
        "organization_id": "org-test",
        "request_id": "req-2b-001",
        "executor_params": {
            "x2text_instance_id": "x2t-001",
            "file_path": "/data/test.pdf",
            "platform_api_key": "sk-test-key",
        },
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def _mock_process_response(extracted_text="hello world", whisper_hash="hash-123"):
    """Build a mock TextExtractionResult."""
    metadata = TextExtractionMetadata(whisper_hash=whisper_hash)
    return TextExtractionResult(
        extracted_text=extracted_text,
        extraction_metadata=metadata,
    )


# --- 1. Happy path ---


class TestHappyPath:
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_extract_returns_success(self, mock_x2text_cls, mock_get_fs):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response("hello")
        mock_x2text.x2text_instance = MagicMock()  # not a Whisperer
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context()
        result = executor.execute(ctx)

        assert result.success is True
        assert result.data[IKeys.EXTRACTED_TEXT] == "hello"

    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_extract_passes_correct_params_to_x2text(
        self, mock_x2text_cls, mock_get_fs
    ):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response()
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context(
            executor_params={
                "x2text_instance_id": "x2t-002",
                "file_path": "/data/doc.pdf",
                "platform_api_key": "sk-key",
                "usage_kwargs": {"org": "test-org"},
            }
        )
        executor.execute(ctx)

        mock_x2text_cls.assert_called_once()
        call_kwargs = mock_x2text_cls.call_args
        assert call_kwargs.kwargs.get("adapter_instance_id") == "x2t-002" or (
            call_kwargs.args
            and len(call_kwargs.args) > 1
            and call_kwargs.args[1] == "x2t-002"
        )


# --- 2. With highlight (LLMWhisperer) ---


class TestWithHighlight:
    @patch("executor.executors.legacy_executor.ToolUtils.dump_json")
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_highlight_with_whisperer_v2(
        self, mock_x2text_cls, mock_get_fs, mock_dump
    ):
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import LLMWhispererV2

        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response()
        # Make isinstance check pass for LLMWhispererV2
        mock_x2text.x2text_instance = MagicMock(spec=LLMWhispererV2)
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context(
            executor_params={
                "x2text_instance_id": "x2t-whisperer",
                "file_path": "/data/test.pdf",
                "platform_api_key": "sk-key",
                "enable_highlight": True,
                "execution_data_dir": "/data/run",
                "tool_execution_metadata": {},
            }
        )
        result = executor.execute(ctx)

        assert result.success is True
        # Verify enable_highlight was passed to process()
        mock_x2text.process.assert_called_once()
        call_kwargs = mock_x2text.process.call_args.kwargs
        assert call_kwargs.get("enable_highlight") is True

    @patch("executor.executors.legacy_executor.ToolUtils.dump_json")
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_highlight_with_whisperer_v1(
        self, mock_x2text_cls, mock_get_fs, mock_dump
    ):
        from unstract.sdk1.adapters.x2text.llm_whisperer.src import LLMWhisperer

        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response()
        mock_x2text.x2text_instance = MagicMock(spec=LLMWhisperer)
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context(
            executor_params={
                "x2text_instance_id": "x2t-whisperer-v1",
                "file_path": "/data/test.pdf",
                "platform_api_key": "sk-key",
                "enable_highlight": True,
                "execution_data_dir": "/data/run",
                "tool_execution_metadata": {},
            }
        )
        result = executor.execute(ctx)

        assert result.success is True
        call_kwargs = mock_x2text.process.call_args.kwargs
        assert call_kwargs.get("enable_highlight") is True


# --- 3. Without highlight (non-Whisperer) ---


class TestWithoutHighlight:
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_no_highlight_for_non_whisperer(self, mock_x2text_cls, mock_get_fs):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response()
        # Generic adapter — not LLMWhisperer
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context(
            executor_params={
                "x2text_instance_id": "x2t-generic",
                "file_path": "/data/test.pdf",
                "platform_api_key": "sk-key",
                "enable_highlight": True,  # requested but adapter doesn't support it
            }
        )
        result = executor.execute(ctx)

        assert result.success is True
        # enable_highlight should NOT be in process() call
        call_kwargs = mock_x2text.process.call_args.kwargs
        assert "enable_highlight" not in call_kwargs

    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_highlight_false_skips_whisperer_branch(
        self, mock_x2text_cls, mock_get_fs
    ):
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import LLMWhispererV2

        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response()
        mock_x2text.x2text_instance = MagicMock(spec=LLMWhispererV2)
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context(
            executor_params={
                "x2text_instance_id": "x2t-whisperer",
                "file_path": "/data/test.pdf",
                "platform_api_key": "sk-key",
                "enable_highlight": False,  # highlight disabled
            }
        )
        result = executor.execute(ctx)

        assert result.success is True
        call_kwargs = mock_x2text.process.call_args.kwargs
        assert "enable_highlight" not in call_kwargs


# --- 4. AdapterError → failure result ---


class TestAdapterError:
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_adapter_error_returns_failure(self, mock_x2text_cls, mock_get_fs):
        from unstract.sdk1.adapters.exceptions import AdapterError

        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text.x2text_instance.get_name.return_value = "TestExtractor"
        mock_x2text.process.side_effect = AdapterError("connection timeout")
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context()
        result = executor.execute(ctx)

        assert result.success is False
        assert "TestExtractor" in result.error
        assert "connection timeout" in result.error


# --- 5. Missing required params ---


class TestMissingParams:
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_missing_x2text_instance_id(self, mock_x2text_cls, mock_get_fs):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        ctx = _make_context(
            executor_params={
                "file_path": "/data/test.pdf",
                "platform_api_key": "sk-key",
            }
        )
        result = executor.execute(ctx)

        assert result.success is False
        assert "x2text_instance_id" in result.error
        mock_x2text_cls.assert_not_called()

    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_missing_file_path(self, mock_x2text_cls, mock_get_fs):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        ctx = _make_context(
            executor_params={
                "x2text_instance_id": "x2t-001",
                "platform_api_key": "sk-key",
            }
        )
        result = executor.execute(ctx)

        assert result.success is False
        assert "file_path" in result.error
        mock_x2text_cls.assert_not_called()

    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_missing_both_params(self, mock_x2text_cls, mock_get_fs):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        ctx = _make_context(executor_params={"platform_api_key": "sk-key"})
        result = executor.execute(ctx)

        assert result.success is False
        assert "x2text_instance_id" in result.error
        assert "file_path" in result.error


# --- 6. Metadata update for tool source ---


class TestMetadataToolSource:
    @patch("executor.executors.legacy_executor.ToolUtils.dump_json")
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_tool_source_writes_metadata(
        self, mock_x2text_cls, mock_get_fs, mock_dump
    ):
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import LLMWhispererV2

        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response(
            whisper_hash="whash-456"
        )
        mock_x2text.x2text_instance = MagicMock(spec=LLMWhispererV2)
        mock_x2text_cls.return_value = mock_x2text
        mock_fs = MagicMock()
        mock_get_fs.return_value = mock_fs

        tool_meta = {}
        ctx = _make_context(
            execution_source="tool",
            executor_params={
                "x2text_instance_id": "x2t-whisperer",
                "file_path": "/data/test.pdf",
                "platform_api_key": "sk-key",
                "enable_highlight": True,
                "execution_data_dir": "/run/data",
                "tool_execution_metadata": tool_meta,
            },
        )
        result = executor.execute(ctx)

        assert result.success is True
        # ToolUtils.dump_json should have been called
        mock_dump.assert_called_once()
        dump_kwargs = mock_dump.call_args.kwargs
        assert dump_kwargs["file_to_dump"] == str(
            Path("/run/data") / IKeys.METADATA_FILE
        )
        assert dump_kwargs["json_to_dump"] == {
            X2TextConstants.WHISPER_HASH: "whash-456"
        }
        assert dump_kwargs["fs"] is mock_fs
        # tool_exec_metadata should be updated in-place
        assert tool_meta[X2TextConstants.WHISPER_HASH] == "whash-456"


# --- 7. IDE source skips metadata ---


class TestMetadataIDESource:
    @patch("executor.executors.legacy_executor.ToolUtils.dump_json")
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_ide_source_skips_metadata(
        self, mock_x2text_cls, mock_get_fs, mock_dump
    ):
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import LLMWhispererV2

        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response()
        mock_x2text.x2text_instance = MagicMock(spec=LLMWhispererV2)
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context(
            execution_source="ide",
            executor_params={
                "x2text_instance_id": "x2t-whisperer",
                "file_path": "/data/test.pdf",
                "platform_api_key": "sk-key",
                "enable_highlight": True,
            },
        )
        result = executor.execute(ctx)

        assert result.success is True
        mock_dump.assert_not_called()


# --- 8. FileUtils routing ---


class TestFileUtilsRouting:
    @patch("executor.executors.file_utils.EnvHelper.get_storage")
    def test_ide_returns_permanent_storage(self, mock_get_storage):
        from executor.executors.file_utils import FileUtils
        from unstract.sdk1.file_storage.constants import StorageType

        mock_get_storage.return_value = MagicMock()
        FileUtils.get_fs_instance("ide")

        mock_get_storage.assert_called_once_with(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )

    @patch("executor.executors.file_utils.EnvHelper.get_storage")
    def test_tool_returns_temporary_storage(self, mock_get_storage):
        from executor.executors.file_utils import FileUtils
        from unstract.sdk1.file_storage.constants import StorageType

        mock_get_storage.return_value = MagicMock()
        FileUtils.get_fs_instance("tool")

        mock_get_storage.assert_called_once_with(
            storage_type=StorageType.SHARED_TEMPORARY,
            env_name=FileStorageKeys.TEMPORARY_REMOTE_STORAGE,
        )

    def test_invalid_source_raises_value_error(self):
        from executor.executors.file_utils import FileUtils

        with pytest.raises(ValueError, match="Invalid execution source"):
            FileUtils.get_fs_instance("unknown")


# --- 9. Orchestrator integration ---


class TestOrchestratorIntegration:
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_orchestrator_extract_returns_success(
        self, mock_x2text_cls, mock_get_fs
    ):
        _register_legacy()
        orchestrator = ExecutionOrchestrator()

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response("extracted!")
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context()
        result = orchestrator.execute(ctx)

        assert result.success is True
        assert result.data[IKeys.EXTRACTED_TEXT] == "extracted!"


# --- 10. Celery eager-mode ---


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


class TestCeleryEager:
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_eager_extract_returns_success(
        self, mock_x2text_cls, mock_get_fs, eager_app
    ):
        _register_legacy()

        mock_x2text = MagicMock()
        mock_x2text.process.return_value = _mock_process_response("celery text")
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context()
        task = eager_app.tasks["execute_extraction"]
        result_dict = task.apply(args=[ctx.to_dict()]).get()
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data[IKeys.EXTRACTED_TEXT] == "celery text"


# --- 11. LegacyExecutorError caught by execute() ---


class TestExecuteErrorCatching:
    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    def test_extraction_error_caught_by_execute(
        self, mock_x2text_cls, mock_get_fs
    ):
        """ExtractionError (a LegacyExecutorError) is caught in execute()
        and mapped to ExecutionResult.failure()."""
        from unstract.sdk1.adapters.exceptions import AdapterError

        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_x2text = MagicMock()
        mock_x2text.x2text_instance = MagicMock()
        mock_x2text.x2text_instance.get_name.return_value = "BadExtractor"
        mock_x2text.process.side_effect = AdapterError("timeout")
        mock_x2text_cls.return_value = mock_x2text
        mock_get_fs.return_value = MagicMock()

        ctx = _make_context()
        result = executor.execute(ctx)

        # Should be a clean failure, NOT an unhandled exception
        assert result.success is False
        assert "BadExtractor" in result.error
        assert "timeout" in result.error

    def test_legacy_executor_error_subclass_caught(self):
        """Any LegacyExecutorError subclass raised by a handler is caught."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        # Monkey-patch _handle_extract to raise a LegacyExecutorError
        def _raise_err(ctx):
            raise LegacyExecutorError(message="custom error", code=422)

        executor._handle_extract = _raise_err

        ctx = _make_context()
        result = executor.execute(ctx)

        assert result.success is False
        assert result.error == "custom error"
