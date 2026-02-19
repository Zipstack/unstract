"""Phase 2F — single_pass_extraction, summarize, agentic_extraction tests.

Verifies:
1. single_pass_extraction delegates to answer_prompt
2. summarize constructs prompt and calls LLM
3. summarize missing params return failure
4. summarize prompt includes prompt_keys
5. agentic_extraction raises LegacyExecutorError (plugin-dependent)
"""

from unittest.mock import MagicMock, patch

import pytest

from unstract.sdk1.execution.context import ExecutionContext
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

    if "legacy" not in ExecutorRegistry.list_executors():
        ExecutorRegistry.register(LegacyExecutor)


def _make_context(**overrides):
    defaults = {
        "executor_name": "legacy",
        "operation": "summarize",
        "run_id": "run-2f-001",
        "execution_source": "tool",
        "organization_id": "org-test",
        "request_id": "req-2f-001",
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


# ---------------------------------------------------------------------------
# 1. single_pass_extraction delegates to answer_prompt
# ---------------------------------------------------------------------------


class TestSinglePassExtraction:
    def test_delegates_to_answer_prompt(self):
        """single_pass_extraction calls _handle_answer_prompt internally."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        # Mock _handle_answer_prompt so we can verify delegation
        expected_result = ExecutionResult(
            success=True,
            data={"output": {"field1": "value1"}, "metadata": {}, "metrics": {}},
        )
        executor._handle_answer_prompt = MagicMock(return_value=expected_result)

        ctx = _make_context(operation="single_pass_extraction")
        result = executor.execute(ctx)

        assert result.success is True
        assert result.data["output"]["field1"] == "value1"
        executor._handle_answer_prompt.assert_called_once_with(ctx)

    def test_delegates_failure_too(self):
        """Failures from answer_prompt propagate through single_pass."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        fail_result = ExecutionResult.failure(error="some error")
        executor._handle_answer_prompt = MagicMock(return_value=fail_result)

        ctx = _make_context(operation="single_pass_extraction")
        result = executor.execute(ctx)

        assert result.success is False
        assert "some error" in result.error


# ---------------------------------------------------------------------------
# 2. summarize
# ---------------------------------------------------------------------------


def _make_summarize_params(**overrides):
    """Build executor_params for summarize operation."""
    defaults = {
        "llm_adapter_instance_id": "llm-001",
        "summarize_prompt": "Summarize the following document.",
        "context": "This is a long document with lots of content.",
        "prompt_keys": ["invoice_number", "total_amount"],
        "PLATFORM_SERVICE_API_KEY": "test-key",
    }
    defaults.update(overrides)
    return defaults


class TestSummarize:
    @patch("executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps")
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_summarize_success(self, mock_shim_cls, mock_get_deps):
        """Successful summarize returns data with summary text."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        # Set up mock LLM
        mock_llm_cls = MagicMock()
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        mock_get_deps.return_value = (
            MagicMock(),   # AnswerPromptService
            MagicMock(),   # RetrievalService
            MagicMock(),   # VariableReplacementService
            MagicMock(),   # Index
            mock_llm_cls,  # LLM
            MagicMock(),   # EmbeddingCompat
            MagicMock(),   # VectorDB
        )

        # Mock AnswerPromptService.run_completion
        with patch(
            "executor.executors.answer_prompt.AnswerPromptService.run_completion",
            return_value="This is a summary of the document.",
        ):
            ctx = _make_context(
                operation="summarize",
                executor_params=_make_summarize_params(),
            )
            result = executor.execute(ctx)

        assert result.success is True
        assert result.data["data"] == "This is a summary of the document."

    @patch("executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps")
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_summarize_prompt_includes_keys(self, mock_shim_cls, mock_get_deps):
        """The summarize prompt includes prompt_keys."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_llm_cls = MagicMock()
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        mock_get_deps.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            mock_llm_cls, MagicMock(), MagicMock(),
        )

        captured_prompt = {}

        def capture_run_completion(llm, prompt, **kwargs):
            captured_prompt["value"] = prompt
            return "summary"

        with patch(
            "executor.executors.answer_prompt.AnswerPromptService.run_completion",
            side_effect=capture_run_completion,
        ):
            ctx = _make_context(
                operation="summarize",
                executor_params=_make_summarize_params(
                    prompt_keys=["name", "address"],
                ),
            )
            executor.execute(ctx)

        assert "name" in captured_prompt["value"]
        assert "address" in captured_prompt["value"]

    @patch("executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps")
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_summarize_no_prompt_keys(self, mock_shim_cls, mock_get_deps):
        """Summarize works without prompt_keys."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_llm_cls = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_get_deps.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            mock_llm_cls, MagicMock(), MagicMock(),
        )

        with patch(
            "executor.executors.answer_prompt.AnswerPromptService.run_completion",
            return_value="summary without keys",
        ):
            params = _make_summarize_params()
            del params["prompt_keys"]
            ctx = _make_context(
                operation="summarize",
                executor_params=params,
            )
            result = executor.execute(ctx)

        assert result.success is True
        assert result.data["data"] == "summary without keys"

    def test_summarize_missing_llm_adapter(self):
        """Missing llm_adapter_instance_id returns failure."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        params = _make_summarize_params(llm_adapter_instance_id="")
        ctx = _make_context(
            operation="summarize",
            executor_params=params,
        )
        result = executor.execute(ctx)

        assert result.success is False
        assert "llm_adapter_instance_id" in result.error

    def test_summarize_missing_context(self):
        """Missing context returns failure."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        params = _make_summarize_params(context="")
        ctx = _make_context(
            operation="summarize",
            executor_params=params,
        )
        result = executor.execute(ctx)

        assert result.success is False
        assert "context" in result.error

    @patch("executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps")
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_summarize_llm_error(self, mock_shim_cls, mock_get_deps):
        """LLM errors are wrapped in ExecutionResult.failure."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_llm_cls = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        mock_get_deps.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            mock_llm_cls, MagicMock(), MagicMock(),
        )

        with patch(
            "executor.executors.answer_prompt.AnswerPromptService.run_completion",
            side_effect=Exception("LLM unavailable"),
        ):
            ctx = _make_context(
                operation="summarize",
                executor_params=_make_summarize_params(),
            )
            result = executor.execute(ctx)

        assert result.success is False
        assert "summarization" in result.error.lower() or "LLM" in result.error

    @patch("executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps")
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_summarize_creates_llm_with_correct_adapter(
        self, mock_shim_cls, mock_get_deps
    ):
        """LLM is instantiated with the provided adapter instance ID."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        mock_llm_cls = MagicMock()
        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        mock_get_deps.return_value = (
            MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            mock_llm_cls, MagicMock(), MagicMock(),
        )

        with patch(
            "executor.executors.answer_prompt.AnswerPromptService.run_completion",
            return_value="summary",
        ):
            ctx = _make_context(
                operation="summarize",
                executor_params=_make_summarize_params(
                    llm_adapter_instance_id="custom-llm-42",
                ),
            )
            executor.execute(ctx)

        mock_llm_cls.assert_called_once()
        call_kwargs = mock_llm_cls.call_args
        assert call_kwargs.kwargs["adapter_instance_id"] == "custom-llm-42"


# ---------------------------------------------------------------------------
# 3. agentic_extraction
# ---------------------------------------------------------------------------


class TestAgenticExtraction:
    def test_returns_failure(self):
        """agentic_extraction returns failure (plugin not available)."""
        _register_legacy()
        executor = ExecutorRegistry.get("legacy")

        ctx = _make_context(operation="agentic_extraction")
        result = executor.execute(ctx)

        assert result.success is False
        assert "agentic extraction" in result.error.lower()
        assert "plugin" in result.error.lower()

    def test_orchestrator_wraps_error(self):
        """ExecutionOrchestrator also returns failure for agentic."""
        from unstract.sdk1.execution.orchestrator import ExecutionOrchestrator

        _register_legacy()
        orchestrator = ExecutionOrchestrator()
        ctx = _make_context(operation="agentic_extraction")
        result = orchestrator.execute(ctx)

        assert result.success is False
        assert "plugin" in result.error.lower()
