"""Phase 2A — LegacyExecutor scaffold tests.

Verifies:
1. Registration in ExecutorRegistry
2. Name property
3. Unsupported operation handling
4. Each operation raises NotImplementedError
5. Orchestrator wraps NotImplementedError as failure
6. Celery eager-mode chain
7. Dispatch table coverage (every Operation has a handler)
8. Constants importable
9. DTOs importable
10. Exceptions standalone (no Flask dependency)
"""

import pytest

from unstract.sdk1.execution.context import ExecutionContext, Operation
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
    """Import executor.executors to trigger LegacyExecutor registration."""
    from executor.executors.legacy_executor import LegacyExecutor  # noqa: F401

    ExecutorRegistry.register(LegacyExecutor)


def _make_context(**overrides):
    defaults = {
        "executor_name": "legacy",
        "operation": "extract",
        "run_id": "run-2a-001",
        "execution_source": "tool",
        "organization_id": "org-test",
        "request_id": "req-2a-001",
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


# --- 1. Registration ---


class TestRegistration:
    def test_legacy_in_registry(self):
        _register_legacy()
        assert "legacy" in ExecutorRegistry.list_executors()


# --- 2. Name ---


class TestName:
    def test_name_is_legacy(self):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")
        assert executor.name == "legacy"


# --- 3. Unsupported operation ---


class TestUnsupportedOperation:
    def test_unsupported_operation_returns_failure(self):
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")
        ctx = _make_context(operation="totally_unknown_op")
        result = executor.execute(ctx)

        assert result.success is False
        assert "does not support operation" in result.error
        assert "totally_unknown_op" in result.error


# --- 4. All operations are implemented (no stubs remain) ---
# TestHandlerStubs and TestOrchestratorWrapping removed:
# All operations (extract, index, answer_prompt, single_pass_extraction,
# summarize, agentic_extraction) are now fully implemented.


# --- 6. Celery eager-mode chain ---


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


class TestCeleryEagerChain:
    def test_eager_unsupported_op_returns_failure(self, eager_app):
        """execute_extraction with an unsupported operation returns failure."""
        _register_legacy()

        ctx = _make_context(operation="totally_unknown_op")
        task = eager_app.tasks["execute_extraction"]
        result_dict = task.apply(args=[ctx.to_dict()]).get()
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is False
        assert "does not support operation" in result.error


# --- 7. Dispatch table coverage ---


class TestDispatchTableCoverage:
    def test_every_operation_has_handler(self):
        from executor.executors.legacy_executor import LegacyExecutor

        for op in Operation:
            assert op.value in LegacyExecutor._OPERATION_MAP, (
                f"Operation {op.value} missing from _OPERATION_MAP"
            )


# --- 8. Constants importable ---


class TestConstants:
    def test_prompt_service_constants(self):
        from executor.executors.constants import PromptServiceConstants

        assert hasattr(PromptServiceConstants, "TOOL_ID")
        assert PromptServiceConstants.TOOL_ID == "tool_id"

    def test_retrieval_strategy(self):
        from executor.executors.constants import RetrievalStrategy

        assert RetrievalStrategy.SIMPLE.value == "simple"
        assert RetrievalStrategy.SUBQUESTION.value == "subquestion"

    def test_run_level(self):
        from executor.executors.constants import RunLevel

        assert RunLevel.RUN.value == "RUN"
        assert RunLevel.EVAL.value == "EVAL"


# --- 9. DTOs importable ---


class TestDTOs:
    def test_chunking_config(self):
        from executor.executors.dto import ChunkingConfig

        cfg = ChunkingConfig(chunk_size=512, chunk_overlap=64)
        assert cfg.chunk_size == 512

    def test_chunking_config_zero_raises(self):
        from executor.executors.dto import ChunkingConfig

        with pytest.raises(ValueError, match="zero chunks"):
            ChunkingConfig(chunk_size=0, chunk_overlap=0)

    def test_file_info(self):
        from executor.executors.dto import FileInfo

        fi = FileInfo(file_path="/tmp/test.pdf", file_hash="abc123")
        assert fi.file_path == "/tmp/test.pdf"

    def test_instance_identifiers(self):
        from executor.executors.dto import InstanceIdentifiers

        ids = InstanceIdentifiers(
            embedding_instance_id="emb-1",
            vector_db_instance_id="vdb-1",
            x2text_instance_id="x2t-1",
            llm_instance_id="llm-1",
            tool_id="tool-1",
        )
        assert ids.tool_id == "tool-1"

    def test_processing_options(self):
        from executor.executors.dto import ProcessingOptions

        opts = ProcessingOptions(reindex=True)
        assert opts.reindex is True
        assert opts.enable_highlight is False


# --- 10. Exceptions standalone ---


class TestExceptions:
    def test_legacy_executor_error_has_code_and_message(self):
        from executor.executors.exceptions import LegacyExecutorError

        err = LegacyExecutorError(message="test error", code=418)
        assert err.message == "test error"
        assert err.code == 418
        assert str(err) == "test error"

    def test_extraction_error_has_code_and_message(self):
        from executor.executors.exceptions import ExtractionError

        err = ExtractionError(message="extraction failed", code=500)
        assert err.message == "extraction failed"
        assert err.code == 500

    def test_no_flask_import(self):
        """Verify exceptions module does NOT import Flask."""
        import importlib
        import sys

        # Ensure fresh import
        mod_name = "executor.executors.exceptions"
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])
        else:
            importlib.import_module(mod_name)

        # Check that no flask modules were pulled in
        flask_modules = [m for m in sys.modules if m.startswith("flask")]
        assert flask_modules == [], (
            f"Flask modules imported: {flask_modules}"
        )

    def test_custom_data_error_signature(self):
        from executor.executors.exceptions import CustomDataError

        err = CustomDataError(
            variable="invoice_num", reason="not found", is_ide=True
        )
        assert "invoice_num" in err.message
        assert "not found" in err.message
        assert "Prompt Studio" in err.message

    def test_custom_data_error_tool_mode(self):
        from executor.executors.exceptions import CustomDataError

        err = CustomDataError(
            variable="order_id", reason="missing", is_ide=False
        )
        assert "API request" in err.message

    def test_missing_field_error(self):
        from executor.executors.exceptions import MissingFieldError

        err = MissingFieldError(missing_fields=["tool_id", "file_path"])
        assert "tool_id" in err.message
        assert "file_path" in err.message

    def test_bad_request_defaults(self):
        from executor.executors.exceptions import BadRequest

        err = BadRequest()
        assert err.code == 400
        assert "Bad Request" in err.message

    def test_rate_limit_error_defaults(self):
        from executor.executors.exceptions import RateLimitError

        err = RateLimitError()
        assert err.code == 429
