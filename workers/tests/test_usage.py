"""Phase 2G — Usage tracking tests.

Verifies:
1. UsageHelper.push_usage_data wraps Audit correctly
2. Invalid kwargs returns False
3. Invalid platform_api_key returns False
4. Audit exceptions are caught and return False
5. format_float_positional formats correctly
6. SDK1 adapters already push usage (integration check)
7. answer_prompt handler returns metrics in ExecutionResult
"""

from unittest.mock import MagicMock, patch

import pytest

from executor.executors.usage import UsageHelper


# ---------------------------------------------------------------------------
# 1. push_usage_data success
# ---------------------------------------------------------------------------


class TestPushUsageData:
    @patch("unstract.sdk1.audit.Audit")
    def test_push_success(self, mock_audit_cls):
        """Successful push returns True and calls Audit."""
        mock_audit = MagicMock()
        mock_audit_cls.return_value = mock_audit

        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs={"run_id": "run-001", "execution_id": "exec-001"},
            platform_api_key="test-key",
            token_counter=MagicMock(),
            model_name="gpt-4",
        )

        assert result is True
        mock_audit.push_usage_data.assert_called_once()
        call_kwargs = mock_audit.push_usage_data.call_args
        assert call_kwargs.kwargs["platform_api_key"] == "test-key"
        assert call_kwargs.kwargs["model_name"] == "gpt-4"
        assert call_kwargs.kwargs["event_type"] == "llm"

    @patch("unstract.sdk1.audit.Audit")
    def test_push_passes_token_counter(self, mock_audit_cls):
        """Token counter is passed through to Audit."""
        mock_audit = MagicMock()
        mock_audit_cls.return_value = mock_audit
        mock_counter = MagicMock()

        UsageHelper.push_usage_data(
            event_type="embedding",
            kwargs={"run_id": "run-002"},
            platform_api_key="key-2",
            token_counter=mock_counter,
        )

        call_kwargs = mock_audit.push_usage_data.call_args
        assert call_kwargs.kwargs["token_counter"] is mock_counter


# ---------------------------------------------------------------------------
# 2. Invalid kwargs
# ---------------------------------------------------------------------------


class TestPushValidation:
    def test_none_kwargs_returns_false(self):
        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs=None,
            platform_api_key="key",
        )
        assert result is False

    def test_empty_kwargs_returns_false(self):
        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs={},
            platform_api_key="key",
        )
        assert result is False

    def test_non_dict_kwargs_returns_false(self):
        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs="not a dict",
            platform_api_key="key",
        )
        assert result is False


# ---------------------------------------------------------------------------
# 3. Invalid platform_api_key
# ---------------------------------------------------------------------------


class TestPushApiKeyValidation:
    def test_none_key_returns_false(self):
        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs={"run_id": "r1"},
            platform_api_key=None,
        )
        assert result is False

    def test_empty_key_returns_false(self):
        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs={"run_id": "r1"},
            platform_api_key="",
        )
        assert result is False

    def test_non_string_key_returns_false(self):
        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs={"run_id": "r1"},
            platform_api_key=12345,
        )
        assert result is False


# ---------------------------------------------------------------------------
# 4. Audit exceptions are caught
# ---------------------------------------------------------------------------


class TestPushErrorHandling:
    @patch("unstract.sdk1.audit.Audit")
    def test_audit_exception_returns_false(self, mock_audit_cls):
        """Audit errors are caught and return False."""
        mock_audit = MagicMock()
        mock_audit.push_usage_data.side_effect = Exception("Network error")
        mock_audit_cls.return_value = mock_audit

        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs={"run_id": "r1"},
            platform_api_key="key",
            token_counter=MagicMock(),
        )

        assert result is False

    @patch("unstract.sdk1.audit.Audit")
    def test_import_error_returns_false(self, mock_audit_cls):
        """Import errors are caught gracefully."""
        mock_audit_cls.side_effect = ImportError("no module")

        result = UsageHelper.push_usage_data(
            event_type="llm",
            kwargs={"run_id": "r1"},
            platform_api_key="key",
        )

        assert result is False


# ---------------------------------------------------------------------------
# 5. format_float_positional
# ---------------------------------------------------------------------------


class TestFormatFloat:
    def test_normal_float(self):
        assert UsageHelper.format_float_positional(0.0001234) == "0.0001234"

    def test_trailing_zeros_removed(self):
        assert UsageHelper.format_float_positional(1.50) == "1.5"

    def test_integer_value(self):
        assert UsageHelper.format_float_positional(42.0) == "42"

    def test_zero(self):
        assert UsageHelper.format_float_positional(0.0) == "0"

    def test_small_value(self):
        result = UsageHelper.format_float_positional(0.00000001)
        assert "0.00000001" == result

    def test_custom_precision(self):
        result = UsageHelper.format_float_positional(1.123456789, precision=3)
        assert result == "1.123"


# ---------------------------------------------------------------------------
# 6. SDK1 adapters already push usage
# ---------------------------------------------------------------------------


class TestAdapterUsageTracking:
    def test_llm_calls_audit_push(self):
        """Verify the LLM adapter imports and calls Audit.push_usage_data.

        This is a static analysis check — we verify the SDK1 LLM module
        references Audit.push_usage_data, confirming adapters handle
        usage tracking internally.
        """
        import inspect

        from unstract.sdk1.llm import LLM

        source = inspect.getsource(LLM)
        assert "push_usage_data" in source
        assert "Audit" in source


# ---------------------------------------------------------------------------
# 7. answer_prompt handler returns metrics
# ---------------------------------------------------------------------------


class TestMetricsInResult:
    @patch(
        "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
        return_value="doc-id-test",
    )
    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_answer_prompt_returns_metrics(
        self, mock_shim_cls, mock_get_deps, _mock_idx
    ):
        """answer_prompt result includes metrics dict."""
        from unstract.sdk1.execution.context import ExecutionContext
        from unstract.sdk1.execution.registry import ExecutorRegistry

        ExecutorRegistry.clear()
        from executor.executors.legacy_executor import LegacyExecutor

        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)

        executor = ExecutorRegistry.get("legacy")

        # Mock all dependencies
        mock_llm = MagicMock()
        mock_llm.get_metrics.return_value = {"total_tokens": 100}
        mock_llm.get_usage_reason.return_value = "extraction"
        mock_llm.complete.return_value = {
            "response": MagicMock(text="test answer"),
            "highlight_data": [],
            "confidence_data": None,
            "word_confidence_data": None,
            "line_numbers": [],
            "whisper_hash": "",
        }

        mock_llm_cls = MagicMock(return_value=mock_llm)
        mock_index = MagicMock()
        mock_index.return_value.generate_index_key.return_value = "doc-123"

        mock_get_deps.return_value = (
            MagicMock(),   # AnswerPromptService — use real for construct
            MagicMock(),   # RetrievalService
            MagicMock(),   # VariableReplacementService
            mock_index,    # Index
            mock_llm_cls,  # LLM
            MagicMock(),   # EmbeddingCompat
            MagicMock(),   # VectorDB
        )

        # Patch AnswerPromptService methods at their real location
        with patch(
            "executor.executors.answer_prompt.AnswerPromptService.extract_variable",
            return_value="test prompt",
        ), patch(
            "executor.executors.answer_prompt.AnswerPromptService.construct_and_run_prompt",
            return_value="test answer",
        ):
            ctx = ExecutionContext(
                executor_name="legacy",
                operation="answer_prompt",
                run_id="run-metrics-001",
                execution_source="tool",
                organization_id="org-test",
                request_id="req-metrics-001",
                executor_params={
                    "tool_settings": {},
                    "outputs": [
                        {
                            "name": "field1",
                            "prompt": "What is X?",
                            "chunk-size": 512,
                            "chunk-overlap": 64,
                            "vector-db": "vdb-1",
                            "embedding": "emb-1",
                            "x2text_adapter": "x2t-1",
                            "llm": "llm-1",
                            "type": "text",
                            "retrieval-strategy": "simple",
                            "similarity-top-k": 5,
                        },
                    ],
                    "tool_id": "tool-1",
                    "file_hash": "hash123",
                    "file_path": "/tmp/test.txt",
                    "file_name": "test.txt",
                    "PLATFORM_SERVICE_API_KEY": "test-key",
                },
            )
            result = executor.execute(ctx)

        assert result.success is True
        assert "metrics" in result.data
        assert "field1" in result.data["metrics"]

        ExecutorRegistry.clear()
