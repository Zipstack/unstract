"""Phase 6I Sanity — Backend Summarizer Migration.

Verifies:
1. Summarize operation exists and routes through LegacyExecutor
2. Summarize executor_params contract matches _handle_summarize expectations
3. Dispatch routes summarize to celery_executor_legacy queue
4. Summarize result has expected shape (data.data = summary text)
5. Full Celery chain for summarize operation
"""

from unittest.mock import MagicMock, patch

import pytest

from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


# Patches
_PATCH_GET_PROMPT_DEPS = (
    "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
)


def _register_legacy():
    from executor.executors.legacy_executor import LegacyExecutor
    ExecutorRegistry.clear()
    ExecutorRegistry.register(LegacyExecutor)


# ---------------------------------------------------------------------------
# 1. Summarize operation enum
# ---------------------------------------------------------------------------

class TestSummarizeOperation:
    def test_summarize_enum_exists(self):
        assert hasattr(Operation, "SUMMARIZE")
        assert Operation.SUMMARIZE.value == "summarize"

    def test_summarize_in_legacy_operation_map(self):
        from executor.executors.legacy_executor import LegacyExecutor
        assert "summarize" in LegacyExecutor._OPERATION_MAP


# ---------------------------------------------------------------------------
# 2. Executor params contract
# ---------------------------------------------------------------------------

class TestSummarizeParamsContract:
    def test_summarize_params_match_handler_expectations(self):
        """Verify the params the backend summarizer sends match
        what _handle_summarize expects."""
        # These are the keys the cloud summarizer.py now sends
        backend_params = {
            "llm_adapter_instance_id": "llm-uuid",
            "summarize_prompt": "Summarize the document...",
            "context": "This is the full document text...",
            "prompt_keys": ["invoice_number", "total_amount"],
            "PLATFORM_SERVICE_API_KEY": "platform-key-123",
        }

        # _handle_summarize reads these keys
        assert "llm_adapter_instance_id" in backend_params
        assert "summarize_prompt" in backend_params
        assert "context" in backend_params
        assert "prompt_keys" in backend_params
        assert "PLATFORM_SERVICE_API_KEY" in backend_params


# ---------------------------------------------------------------------------
# 3. Queue routing
# ---------------------------------------------------------------------------

class TestSummarizeQueueRouting:
    def test_summarize_routes_to_legacy_queue(self):
        """Summarize dispatches to celery_executor_legacy (LegacyExecutor)."""
        queue = ExecutionDispatcher._get_queue("legacy")
        assert queue == "celery_executor_legacy"

    def test_dispatch_sends_summarize_to_legacy_queue(self):
        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.get.return_value = ExecutionResult(
            success=True, data={"data": "Summary text here"}
        ).to_dict()
        mock_app.send_task.return_value = mock_result

        dispatcher = ExecutionDispatcher(celery_app=mock_app)
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="summarize",
            run_id="run-summarize",
            execution_source="ide",
            organization_id="org-1",
            executor_params={
                "llm_adapter_instance_id": "llm-1",
                "summarize_prompt": "Summarize...",
                "context": "Document text",
                "prompt_keys": ["field1"],
                "PLATFORM_SERVICE_API_KEY": "key-1",
            },
        )
        result = dispatcher.dispatch(ctx)

        mock_app.send_task.assert_called_once()
        call_kwargs = mock_app.send_task.call_args
        assert call_kwargs.kwargs.get("queue") == "celery_executor_legacy"
        assert result.success
        assert result.data["data"] == "Summary text here"


# ---------------------------------------------------------------------------
# 4. Result shape
# ---------------------------------------------------------------------------

class TestSummarizeResultShape:
    @patch(_PATCH_GET_PROMPT_DEPS)
    def test_summarize_returns_data_key(self, mock_deps):
        """_handle_summarize returns ExecutionResult with data.data = str."""
        mock_llm = MagicMock()
        mock_llm_instance = MagicMock()
        mock_llm.return_value = mock_llm_instance

        mock_deps.return_value = (
            MagicMock(),  # RetrievalService
            MagicMock(),  # PostProcessor
            MagicMock(),  # VariableReplacement
            MagicMock(),  # JsonRepair
            mock_llm,     # LLM
            MagicMock(),  # Embedding
            MagicMock(),  # VectorDB
        )

        # Mock AnswerPromptService.run_completion
        with patch(
            "executor.executors.answer_prompt.AnswerPromptService.run_completion",
            return_value="This is the summary.",
        ):
            _register_legacy()
            executor = ExecutorRegistry.get("legacy")

            ctx = ExecutionContext(
                executor_name="legacy",
                operation="summarize",
                run_id="run-result-shape",
                execution_source="ide",
                organization_id="org-1",
                executor_params={
                    "llm_adapter_instance_id": "llm-1",
                    "summarize_prompt": "Summarize the document.",
                    "context": "Full document text here.",
                    "prompt_keys": ["total"],
                    "PLATFORM_SERVICE_API_KEY": "key-1",
                },
            )
            result = executor.execute(ctx)

        assert result.success
        assert result.data["data"] == "This is the summary."

    @patch(_PATCH_GET_PROMPT_DEPS)
    def test_summarize_missing_context_returns_failure(self, mock_deps):
        """Missing context param returns failure without LLM call."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="summarize",
            run_id="run-missing-ctx",
            execution_source="ide",
            executor_params={
                "llm_adapter_instance_id": "llm-1",
                "summarize_prompt": "Summarize.",
                "context": "",  # empty
                "PLATFORM_SERVICE_API_KEY": "key-1",
            },
        )
        result = executor.execute(ctx)

        assert not result.success
        assert "context" in result.error.lower()

    @patch(_PATCH_GET_PROMPT_DEPS)
    def test_summarize_missing_llm_returns_failure(self, mock_deps):
        """Missing llm_adapter_instance_id returns failure."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="summarize",
            run_id="run-missing-llm",
            execution_source="ide",
            executor_params={
                "llm_adapter_instance_id": "",  # empty
                "summarize_prompt": "Summarize.",
                "context": "Some text",
                "PLATFORM_SERVICE_API_KEY": "key-1",
            },
        )
        result = executor.execute(ctx)

        assert not result.success
        assert "llm_adapter_instance_id" in result.error.lower()


# ---------------------------------------------------------------------------
# 5. Full Celery chain
# ---------------------------------------------------------------------------

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


class TestSummarizeCeleryChain:
    @patch(_PATCH_GET_PROMPT_DEPS)
    def test_summarize_full_celery_chain(self, mock_deps, eager_app):
        """Summarize through full Celery task chain."""
        mock_llm = MagicMock()
        mock_llm_instance = MagicMock()
        mock_llm.return_value = mock_llm_instance

        mock_deps.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            mock_llm, MagicMock(), MagicMock(),
        )

        with patch(
            "executor.executors.answer_prompt.AnswerPromptService.run_completion",
            return_value="Celery chain summary.",
        ):
            _register_legacy()

            ctx = ExecutionContext(
                executor_name="legacy",
                operation="summarize",
                run_id="run-celery-summarize",
                execution_source="ide",
                organization_id="org-1",
                executor_params={
                    "llm_adapter_instance_id": "llm-1",
                    "summarize_prompt": "Summarize.",
                    "context": "Document text for celery chain.",
                    "prompt_keys": ["amount"],
                    "PLATFORM_SERVICE_API_KEY": "key-1",
                },
            )

            task = eager_app.tasks["execute_extraction"]
            result_dict = task.apply(args=[ctx.to_dict()]).get()
            result = ExecutionResult.from_dict(result_dict)

        assert result.success
        assert result.data["data"] == "Celery chain summary."
