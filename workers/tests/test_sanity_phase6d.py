"""Phase 6D Sanity — LegacyExecutor plugin integration.

Verifies:
1. TABLE type raises LegacyExecutorError with routing guidance
2. LINE_ITEM type raises LegacyExecutorError (not supported)
3. Challenge plugin invoked when enable_challenge=True + plugin installed
4. Challenge skipped when plugin not installed (graceful degradation)
5. Challenge skipped when enable_challenge=False
6. Challenge skipped when challenge_llm not configured
7. Evaluation plugin invoked when eval_settings.evaluate=True + plugin installed
8. Evaluation skipped when plugin not installed
9. Evaluation skipped when eval_settings.evaluate=False
10. Challenge runs before evaluation (order matters)
11. Challenge mutates structured_output (via mock)
"""

from unittest.mock import MagicMock, patch

import pytest
from executor.executors.answer_prompt import AnswerPromptService
from executor.executors.constants import PromptServiceConstants as PSKeys
from executor.executors.exceptions import LegacyExecutorError
from unstract.sdk1.execution.result import ExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    output_type="TEXT",
    enable_highlight=False,
    enable_challenge=False,
    challenge_llm="",
    eval_settings=None,
):
    """Build a minimal ExecutionContext for answer_prompt tests."""
    from unstract.sdk1.execution.context import ExecutionContext

    prompt_output = {
        PSKeys.NAME: "field1",
        PSKeys.PROMPT: "What is X?",
        PSKeys.PROMPTX: "What is X?",
        PSKeys.TYPE: output_type,
        PSKeys.CHUNK_SIZE: 0,
        PSKeys.CHUNK_OVERLAP: 0,
        PSKeys.LLM: "llm-123",
        PSKeys.EMBEDDING: "emb-123",
        PSKeys.VECTOR_DB: "vdb-123",
        PSKeys.X2TEXT_ADAPTER: "x2t-123",
        PSKeys.RETRIEVAL_STRATEGY: "simple",
    }
    if eval_settings:
        prompt_output[PSKeys.EVAL_SETTINGS] = eval_settings

    tool_settings = {
        PSKeys.PREAMBLE: "",
        PSKeys.POSTAMBLE: "",
        PSKeys.GRAMMAR: [],
        PSKeys.ENABLE_HIGHLIGHT: enable_highlight,
        PSKeys.ENABLE_CHALLENGE: enable_challenge,
    }
    if challenge_llm:
        tool_settings[PSKeys.CHALLENGE_LLM] = challenge_llm

    return ExecutionContext(
        executor_name="legacy",
        operation="answer_prompt",
        run_id="run-001",
        execution_source="ide",
        organization_id="org-1",
        executor_params={
            PSKeys.TOOL_SETTINGS: tool_settings,
            PSKeys.OUTPUTS: [prompt_output],
            PSKeys.TOOL_ID: "tool-1",
            PSKeys.FILE_HASH: "hash123",
            PSKeys.FILE_PATH: "/data/doc.txt",
            PSKeys.FILE_NAME: "doc.txt",
            PSKeys.PLATFORM_SERVICE_API_KEY: "key-123",
        },
    )


def _get_executor():
    from executor.executors.legacy_executor import LegacyExecutor
    from unstract.sdk1.execution.registry import ExecutorRegistry

    ExecutorRegistry.clear()
    if "legacy" not in ExecutorRegistry.list_executors():
        ExecutorRegistry.register(LegacyExecutor)
    return ExecutorRegistry.get("legacy")


def _mock_llm():
    """Create a mock LLM that returns a realistic completion dict."""
    llm = MagicMock()
    llm.complete.return_value = {
        PSKeys.RESPONSE: MagicMock(text="42"),
        PSKeys.HIGHLIGHT_DATA: [],
        PSKeys.LINE_NUMBERS: [],
        PSKeys.WHISPER_HASH: "",
    }
    llm.get_usage_reason.return_value = "extraction"
    llm.get_metrics.return_value = {}
    return llm


def _standard_patches(executor, mock_llm_instance):
    """Return common patches for _handle_answer_prompt tests."""
    mock_llm_cls = MagicMock(return_value=mock_llm_instance)
    return {
        "_get_prompt_deps": patch.object(
            executor, "_get_prompt_deps",
            return_value=(
                AnswerPromptService,
                MagicMock(
                    retrieve_complete_context=MagicMock(
                        return_value=["context chunk"]
                    )
                ),
                MagicMock(
                    is_variables_present=MagicMock(return_value=False)
                ),
                None,  # Index
                mock_llm_cls,
                MagicMock(),  # EmbeddingCompat
                MagicMock(),  # VectorDB
            ),
        ),
        "shim": patch(
            "executor.executors.legacy_executor.ExecutorToolShim",
            return_value=MagicMock(),
        ),
        "index_key": patch(
            "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
            return_value="doc-id-1",
        ),
    }


# ---------------------------------------------------------------------------
# 1. TABLE type raises with routing guidance
# ---------------------------------------------------------------------------

class TestTableLineItemGuard:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_table_type_delegates_to_table_executor(
        self, mock_key, mock_shim_cls
    ):
        """TABLE prompts are delegated to TableExtractorExecutor in-process."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(output_type=PSKeys.TABLE)  # "table"
        llm = _mock_llm()
        patches = _standard_patches(executor, llm)

        mock_table_executor = MagicMock()
        mock_table_executor.execute.return_value = ExecutionResult(
            success=True,
            data={"output": {"table_data": "extracted"}, "metadata": {"metrics": {}}},
        )

        with patches["_get_prompt_deps"], patches["shim"], patches["index_key"]:
            with patch(
                "unstract.sdk1.execution.registry.ExecutorRegistry.get",
                return_value=mock_table_executor,
            ):
                result = executor._handle_answer_prompt(ctx)

        assert result.success
        assert result.data["output"]["field1"] == {"table_data": "extracted"}
        mock_table_executor.execute.assert_called_once()
        # Verify the sub-context was built with table executor params
        sub_ctx = mock_table_executor.execute.call_args[0][0]
        assert sub_ctx.executor_name == "table"
        assert sub_ctx.operation == "table_extract"

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_table_type_raises_when_plugin_missing(
        self, mock_key, mock_shim_cls
    ):
        """TABLE prompts raise error when table executor plugin is not installed."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(output_type=PSKeys.TABLE)  # "table"
        llm = _mock_llm()
        patches = _standard_patches(executor, llm)

        with patches["_get_prompt_deps"], patches["shim"], patches["index_key"]:
            with patch(
                "unstract.sdk1.execution.registry.ExecutorRegistry.get",
                side_effect=KeyError("No executor registered with name 'table'"),
            ):
                with pytest.raises(LegacyExecutorError, match="table executor plugin"):
                    executor._handle_answer_prompt(ctx)

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_line_item_type_raises_not_supported(
        self, mock_key, mock_shim_cls
    ):
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(output_type=PSKeys.LINE_ITEM)  # "line-item"
        llm = _mock_llm()
        patches = _standard_patches(executor, llm)

        with patches["_get_prompt_deps"], patches["shim"], patches["index_key"]:
            with pytest.raises(LegacyExecutorError, match="not supported"):
                executor._handle_answer_prompt(ctx)


# ---------------------------------------------------------------------------
# 2. Challenge plugin integration
# ---------------------------------------------------------------------------

class TestChallengeIntegration:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_challenge_invoked_when_enabled_and_installed(
        self, mock_key, mock_shim_cls
    ):
        """Challenge plugin is instantiated and run() called."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(enable_challenge=True, challenge_llm="ch-llm-1")
        llm = _mock_llm()
        mock_challenge_cls = MagicMock()
        mock_challenger = MagicMock()
        mock_challenge_cls.return_value = mock_challenger

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                side_effect=lambda name: (
                    mock_challenge_cls if name == "challenge" else None
                ),
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # Challenge class was instantiated with correct args
        mock_challenge_cls.assert_called_once()
        init_kwargs = mock_challenge_cls.call_args.kwargs
        assert init_kwargs["run_id"] == "run-001"
        assert init_kwargs["platform_key"] == "key-123"
        assert init_kwargs["llm"] is llm
        # run() was called
        mock_challenger.run.assert_called_once()

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_challenge_skipped_when_plugin_not_installed(
        self, mock_key, mock_shim_cls
    ):
        """When challenge enabled but plugin missing, no error."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(enable_challenge=True, challenge_llm="ch-llm-1")
        llm = _mock_llm()

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                return_value=None,
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_challenge_skipped_when_disabled(
        self, mock_key, mock_shim_cls
    ):
        """When enable_challenge=False, plugin loader not called for challenge."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(enable_challenge=False)
        llm = _mock_llm()

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
            ) as mock_get,
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # Plugin loader should NOT have been called for "challenge"
        for c in mock_get.call_args_list:
            assert c.args[0] != "challenge", (
                "ExecutorPluginLoader.get('challenge') should not be called"
            )

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_challenge_skipped_when_no_challenge_llm(
        self, mock_key, mock_shim_cls
    ):
        """When enable_challenge=True but no challenge_llm, skip challenge."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        # enable_challenge=True but challenge_llm="" (empty)
        ctx = _make_context(enable_challenge=True, challenge_llm="")
        llm = _mock_llm()
        mock_challenge_cls = MagicMock()

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                return_value=mock_challenge_cls,
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # Challenge class should NOT be instantiated (no LLM ID)
        mock_challenge_cls.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Evaluation plugin integration
# ---------------------------------------------------------------------------

class TestEvaluationIntegration:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_evaluation_invoked_when_enabled_and_installed(
        self, mock_key, mock_shim_cls
    ):
        """Evaluation plugin is instantiated and run() called."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(
            eval_settings={PSKeys.EVAL_SETTINGS_EVALUATE: True}
        )
        llm = _mock_llm()
        mock_eval_cls = MagicMock()
        mock_evaluator = MagicMock()
        mock_eval_cls.return_value = mock_evaluator

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                side_effect=lambda name: (
                    mock_eval_cls if name == "evaluation" else None
                ),
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        mock_eval_cls.assert_called_once()
        init_kwargs = mock_eval_cls.call_args.kwargs
        assert init_kwargs["platform_key"] == "key-123"
        assert init_kwargs["response"] == "42"  # from mock LLM
        mock_evaluator.run.assert_called_once()

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_evaluation_skipped_when_plugin_not_installed(
        self, mock_key, mock_shim_cls
    ):
        """When evaluation enabled but plugin missing, no error."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(
            eval_settings={PSKeys.EVAL_SETTINGS_EVALUATE: True}
        )
        llm = _mock_llm()

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                return_value=None,
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_evaluation_skipped_when_not_enabled(
        self, mock_key, mock_shim_cls
    ):
        """When no eval_settings or evaluate=False, evaluation skipped."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        # No eval_settings at all
        ctx = _make_context()
        llm = _mock_llm()

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
            ) as mock_get,
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # Plugin loader should NOT have been called for "evaluation"
        for c in mock_get.call_args_list:
            assert c.args[0] != "evaluation", (
                "ExecutorPluginLoader.get('evaluation') should not be called"
            )


# ---------------------------------------------------------------------------
# 4. Challenge runs before evaluation (ordering)
# ---------------------------------------------------------------------------

class TestChallengeBeforeEvaluation:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_challenge_runs_before_evaluation(
        self, mock_key, mock_shim_cls
    ):
        """Challenge mutates structured_output before evaluation reads it."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(
            enable_challenge=True,
            challenge_llm="ch-llm-1",
            eval_settings={PSKeys.EVAL_SETTINGS_EVALUATE: True},
        )
        llm = _mock_llm()

        # Track call order
        call_order = []

        mock_challenge_cls = MagicMock()
        mock_challenger = MagicMock()
        mock_challenger.run.side_effect = lambda: call_order.append("challenge")
        mock_challenge_cls.return_value = mock_challenger

        mock_eval_cls = MagicMock()
        mock_evaluator = MagicMock()
        mock_evaluator.run.side_effect = lambda: call_order.append("evaluation")
        mock_eval_cls.return_value = mock_evaluator

        def plugin_get(name):
            if name == "challenge":
                return mock_challenge_cls
            if name == "evaluation":
                return mock_eval_cls
            return None

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                side_effect=plugin_get,
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        assert call_order == ["challenge", "evaluation"]


# ---------------------------------------------------------------------------
# 5. Challenge mutates structured_output
# ---------------------------------------------------------------------------

class TestChallengeMutation:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_challenge_mutates_structured_output(
        self, mock_key, mock_shim_cls
    ):
        """Challenge plugin can mutate structured_output dict."""
        mock_shim_cls.return_value = MagicMock()
        executor = _get_executor()
        ctx = _make_context(enable_challenge=True, challenge_llm="ch-llm-1")
        llm = _mock_llm()

        def challenge_run_side_effect():
            # Simulate challenge replacing the answer with improved version
            # Access the structured_output passed to constructor
            so = mock_challenge_cls.call_args.kwargs["structured_output"]
            so["field1"] = "improved_42"

        mock_challenge_cls = MagicMock()
        mock_challenger = MagicMock()
        mock_challenger.run.side_effect = challenge_run_side_effect
        mock_challenge_cls.return_value = mock_challenger

        patches = _standard_patches(executor, llm)
        with (
            patches["_get_prompt_deps"],
            patches["shim"],
            patches["index_key"],
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                side_effect=lambda name: (
                    mock_challenge_cls if name == "challenge" else None
                ),
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # The structured_output should contain the mutated value
        assert result.data[PSKeys.OUTPUT]["field1"] == "improved_42"
