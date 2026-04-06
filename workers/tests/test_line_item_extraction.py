"""Tests for LegacyExecutor._run_line_item_extraction (LINE_ITEM type).

Mirrors the structure of TABLE delegation tests in test_sanity_phase6d.py.

Verifies:
1. Plugin missing → LegacyExecutorError with install hint.
2. Plugin success → output written + metrics merged + context propagated.
3. Plugin failure → empty output + error logged.
4. End-to-end through _execute_single_prompt with a LINE_ITEM prompt
   in the structure-tool path (eager Celery + fake plugin).
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from executor.executors.answer_prompt import AnswerPromptService
from executor.executors.constants import PromptServiceConstants as PSKeys
from executor.executors.exceptions import LegacyExecutorError
from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.executor import BaseExecutor
from unstract.sdk1.execution.registry import ExecutorRegistry
from unstract.sdk1.execution.result import ExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure a clean executor registry for every test."""
    ExecutorRegistry.clear()
    yield
    ExecutorRegistry.clear()


def _get_legacy_executor():
    """Register and fetch the LegacyExecutor instance."""
    from executor.executors.legacy_executor import LegacyExecutor

    if "legacy" not in ExecutorRegistry.list_executors():
        ExecutorRegistry.register(LegacyExecutor)
    return ExecutorRegistry.get("legacy")


def _make_line_item_prompt():
    """Build a LINE_ITEM prompt config dict (mirrors _execute_single_prompt
    expectations).
    """
    return {
        PSKeys.NAME: "line_items",
        PSKeys.PROMPT: "Extract all invoice line items.",
        PSKeys.PROMPTX: "Extract all invoice line items.",
        PSKeys.TYPE: PSKeys.LINE_ITEM,
        PSKeys.CHUNK_SIZE: 0,
        PSKeys.CHUNK_OVERLAP: 0,
        PSKeys.LLM: "llm-1",
        PSKeys.EMBEDDING: "emb-1",
        PSKeys.VECTOR_DB: "vdb-1",
        PSKeys.X2TEXT_ADAPTER: "x2t-1",
        PSKeys.RETRIEVAL_STRATEGY: "simple",
    }


def _make_context():
    """Build a minimal ExecutionContext for the answer_prompt path."""
    tool_settings = {
        PSKeys.PREAMBLE: "",
        PSKeys.POSTAMBLE: "",
        PSKeys.GRAMMAR: [],
        PSKeys.ENABLE_HIGHLIGHT: False,
    }
    return ExecutionContext(
        executor_name="legacy",
        operation="answer_prompt",
        run_id="run-line-item-001",
        execution_source="tool",
        organization_id="org-test",
        request_id="req-line-item-001",
        executor_params={
            PSKeys.TOOL_SETTINGS: tool_settings,
            PSKeys.OUTPUTS: [_make_line_item_prompt()],
            PSKeys.TOOL_ID: "tool-1",
            PSKeys.FILE_HASH: "hash123",
            PSKeys.FILE_PATH: "/data/invoice.txt",
            PSKeys.FILE_NAME: "invoice.txt",
            PSKeys.PLATFORM_SERVICE_API_KEY: "pk-test",
        },
    )


def _standard_patches(executor):
    """Common patches needed to drive _handle_answer_prompt → _execute_single_prompt
    until it reaches the LINE_ITEM branch.
    """
    llm = MagicMock(name="llm")
    llm.get_metrics.return_value = {}
    mock_llm_cls = MagicMock(return_value=llm)
    return {
        "_get_prompt_deps": patch.object(
            executor,
            "_get_prompt_deps",
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
# Fake LineItemExecutor plugins
# ---------------------------------------------------------------------------


def _make_success_plugin(
    output_value=None,
    metrics=None,
    context_list=None,
):
    """Build a fake plugin class that returns a success ExecutionResult."""
    payload = {"output": output_value or {"items": [{"sku": "A1", "qty": 2}]}}
    if metrics is not None:
        payload["metadata"] = {"metrics": metrics}
    if context_list is not None:
        payload["context"] = context_list

    class _SuccessPlugin(BaseExecutor):
        @property
        def name(self) -> str:
            return "line_item"

        def execute(self, context: ExecutionContext) -> ExecutionResult:
            self.received_context = context
            return ExecutionResult(success=True, data=payload)

    return _SuccessPlugin


def _make_failure_plugin(error="extraction blew up"):
    class _FailurePlugin(BaseExecutor):
        @property
        def name(self) -> str:
            return "line_item"

        def execute(self, context: ExecutionContext) -> ExecutionResult:
            return ExecutionResult.failure(error=error)

    return _FailurePlugin


# ---------------------------------------------------------------------------
# 1. Plugin missing → clear error
# ---------------------------------------------------------------------------


class TestLineItemPluginMissing:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch(
        "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
        return_value="doc-id-1",
    )
    def test_line_item_raises_when_plugin_missing(
        self, _mock_key, _mock_shim_cls
    ):
        """LINE_ITEM prompt raises LegacyExecutorError with install hint."""
        executor = _get_legacy_executor()
        ctx = _make_context()
        patches = _standard_patches(executor)

        with patches["_get_prompt_deps"], patches["shim"], patches["index_key"]:
            with pytest.raises(
                LegacyExecutorError,
                match="line_item_extractor plugin",
            ):
                executor._handle_answer_prompt(ctx)


# ---------------------------------------------------------------------------
# 2. Plugin success → output written + metrics + context
# ---------------------------------------------------------------------------


class TestLineItemPluginSuccess:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch(
        "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
        return_value="doc-id-1",
    )
    def test_success_writes_output_and_merges_metrics(
        self, _mock_key, _mock_shim_cls
    ):
        executor = _get_legacy_executor()
        ctx = _make_context()
        patches = _standard_patches(executor)

        plugin_cls = _make_success_plugin(
            output_value={"items": [{"sku": "A1", "qty": 2}]},
            metrics={"llm_calls": 3},
            context_list=["full file body"],
        )
        # Register so ExecutorRegistry.get("line_item") finds it
        ExecutorRegistry.register(plugin_cls)

        with patches["_get_prompt_deps"], patches["shim"], patches["index_key"]:
            result = executor._handle_answer_prompt(ctx)

        assert result.success is True
        # structured_output[prompt_name] holds the plugin output
        assert result.data["output"]["line_items"] == {
            "items": [{"sku": "A1", "qty": 2}]
        }
        # Metrics are merged under the line_item_extraction sub-key
        prompt_metrics = result.data["metrics"]["line_items"]
        assert prompt_metrics["line_item_extraction"] == {"llm_calls": 3}
        # Context list is propagated to metadata.context
        assert result.data["metadata"][PSKeys.CONTEXT]["line_items"] == [
            "full file body"
        ]

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch(
        "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
        return_value="doc-id-1",
    )
    def test_success_passes_correct_executor_params(
        self, _mock_key, _mock_shim_cls
    ):
        """Verify the sub-context built for the plugin has all expected
        keys with the right values.
        """
        executor = _get_legacy_executor()
        ctx = _make_context()
        patches = _standard_patches(executor)

        captured: dict = {}

        class _CapturePlugin(BaseExecutor):
            @property
            def name(self) -> str:
                return "line_item"

            def execute(self, context: ExecutionContext) -> ExecutionResult:
                captured["ctx"] = context
                return ExecutionResult(success=True, data={"output": {}})

        ExecutorRegistry.register(_CapturePlugin)

        with patches["_get_prompt_deps"], patches["shim"], patches["index_key"]:
            executor._handle_answer_prompt(ctx)

        sub_ctx = captured["ctx"]
        assert sub_ctx.executor_name == "line_item"
        assert sub_ctx.operation == "line_item_extract"
        assert sub_ctx.run_id == "run-line-item-001"
        assert sub_ctx.organization_id == "org-test"

        params = sub_ctx.executor_params
        assert params["llm_adapter_instance_id"] == "llm-1"
        assert params["PLATFORM_SERVICE_API_KEY"] == "pk-test"
        assert params["file_path"] == "/data/invoice.txt"
        assert params["file_name"] == "invoice.txt"
        assert params["tool_id"] == "tool-1"
        assert params["prompt_name"] == "line_items"
        assert params["prompt"] == "Extract all invoice line items."
        # output dict and tool_settings are passed through
        assert params["output"][PSKeys.NAME] == "line_items"
        assert params["output"][PSKeys.TYPE] == PSKeys.LINE_ITEM
        assert PSKeys.PREAMBLE in params["tool_settings"]


# ---------------------------------------------------------------------------
# 3. Plugin failure → empty output + error logged
# ---------------------------------------------------------------------------


class TestLineItemPluginFailure:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch(
        "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
        return_value="doc-id-1",
    )
    def test_failure_writes_empty_output_and_logs(
        self, _mock_key, _mock_shim_cls, caplog
    ):
        executor = _get_legacy_executor()
        ctx = _make_context()
        patches = _standard_patches(executor)

        ExecutorRegistry.register(_make_failure_plugin("plugin error"))

        with patches["_get_prompt_deps"], patches["shim"], patches["index_key"]:
            with caplog.at_level(
                logging.ERROR,
                logger="executor.executors.legacy_executor",
            ):
                result = executor._handle_answer_prompt(ctx)

        assert result.success is True  # answer_prompt itself does not raise
        assert result.data["output"]["line_items"] == ""
        # Failure logged
        assert any(
            "LINE_ITEM extraction failed" in rec.message
            and "plugin error" in rec.message
            for rec in caplog.records
        )


# ---------------------------------------------------------------------------
# 4. End-to-end through Celery eager mode (structure-tool path)
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


def _structure_tool_ctx():
    """Build an answer_prompt context with a single LINE_ITEM prompt for
    the structure-tool path (execution_source='tool').
    """
    tool_settings = {
        PSKeys.PREAMBLE: "Extract carefully.",
        PSKeys.POSTAMBLE: "No commentary.",
        PSKeys.GRAMMAR: [],
        PSKeys.ENABLE_HIGHLIGHT: False,
        PSKeys.ENABLE_CHALLENGE: False,
    }
    return ExecutionContext(
        executor_name="legacy",
        operation="answer_prompt",
        run_id="run-line-item-e2e",
        execution_source="tool",
        organization_id="org-e2e",
        request_id="req-e2e",
        executor_params={
            PSKeys.TOOL_SETTINGS: tool_settings,
            PSKeys.OUTPUTS: [_make_line_item_prompt()],
            PSKeys.TOOL_ID: "tool-e2e",
            PSKeys.FILE_HASH: "hash-e2e",
            PSKeys.FILE_PATH: "/data/rent_roll.txt",
            PSKeys.FILE_NAME: "rent_roll.txt",
            PSKeys.PLATFORM_SERVICE_API_KEY: "pk-e2e",
        },
    )


class TestLineItemEndToEnd:
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch(
        "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
        return_value="doc-id-e2e",
    )
    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch(
        "executor.executors.plugins.loader.ExecutorPluginLoader.get",
        return_value=None,
    )
    def test_celery_eager_chain_with_line_item_plugin(
        self,
        _mock_plugin_loader,
        mock_deps,
        _mock_index_utils,
        _mock_shim_cls,
        eager_app,
    ):
        """Push a LINE_ITEM payload through the full Celery eager chain
        with a fake line_item plugin registered.
        """
        # Re-register LegacyExecutor since the autouse fixture cleared it
        from executor.executors.legacy_executor import LegacyExecutor

        ExecutorRegistry.register(LegacyExecutor)

        # Register fake line_item plugin
        plugin_cls = _make_success_plugin(
            output_value={
                "items": [
                    {"unit": "1A", "rent": 1500},
                    {"unit": "1B", "rent": 1700},
                ]
            },
            metrics={"llm_calls": 2, "tokens": 1234},
            context_list=["rent roll body"],
        )
        ExecutorRegistry.register(plugin_cls)

        # Mock the prompt deps so _execute_single_prompt can run far
        # enough to hit the LINE_ITEM branch
        llm = MagicMock(name="llm")
        llm.get_metrics.return_value = {}
        mock_llm_cls = MagicMock(return_value=llm)
        mock_deps.return_value = (
            AnswerPromptService,
            MagicMock(
                retrieve_complete_context=MagicMock(return_value=["chunk"])
            ),
            MagicMock(is_variables_present=MagicMock(return_value=False)),
            None,
            mock_llm_cls,
            MagicMock(),
            MagicMock(),
        )

        ctx = _structure_tool_ctx()
        task = eager_app.tasks["execute_extraction"]
        async_result = task.apply(args=[ctx.to_dict()])
        result_dict = async_result.get()
        result = ExecutionResult.from_dict(result_dict)

        assert result.success is True
        assert result.data["output"]["line_items"] == {
            "items": [
                {"unit": "1A", "rent": 1500},
                {"unit": "1B", "rent": 1700},
            ]
        }
        assert (
            result.data["metrics"]["line_items"]["line_item_extraction"]
            == {"llm_calls": 2, "tokens": 1234}
        )
