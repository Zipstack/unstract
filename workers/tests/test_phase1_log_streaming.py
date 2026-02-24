"""Phase 1 — Executor log streaming to frontend via Socket.IO.

Tests cover:
- ExecutionContext round-trips log_events_id through to_dict/from_dict
- LogPublisher.log_progress() returns type: "PROGRESS" (not "LOG")
- LogPublisher.log_prompt() still returns type: "LOG" (unchanged)
- ExecutorToolShim with log_events_id: stream_log() publishes progress
- ExecutorToolShim without log_events_id: no publishing, no exceptions
- ExecutorToolShim with failing LogPublisher: no exception raised
- execute_extraction builds component dict when log_events_id present
- execute_extraction skips component dict when log_events_id absent
"""

from unittest.mock import MagicMock, patch

import pytest

from unstract.sdk1.constants import LogLevel
from unstract.sdk1.execution.context import ExecutionContext


# ---------------------------------------------------------------------------
# 1A — ExecutionContext.log_events_id round-trip
# ---------------------------------------------------------------------------


class TestExecutionContextLogEventsId:
    """Verify log_events_id serialization in ExecutionContext."""

    def test_log_events_id_default_is_none(self):
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="r1",
            execution_source="ide",
        )
        assert ctx.log_events_id is None

    def test_log_events_id_round_trips(self):
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="r1",
            execution_source="ide",
            log_events_id="session-abc",
        )
        d = ctx.to_dict()
        assert d["log_events_id"] == "session-abc"

        restored = ExecutionContext.from_dict(d)
        assert restored.log_events_id == "session-abc"

    def test_log_events_id_none_round_trips(self):
        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="r1",
            execution_source="ide",
        )
        d = ctx.to_dict()
        assert d["log_events_id"] is None

        restored = ExecutionContext.from_dict(d)
        assert restored.log_events_id is None

    def test_backward_compat_missing_key(self):
        """from_dict with old payload lacking log_events_id."""
        old_payload = {
            "executor_name": "legacy",
            "operation": "extract",
            "run_id": "r1",
            "execution_source": "ide",
        }
        ctx = ExecutionContext.from_dict(old_payload)
        assert ctx.log_events_id is None


# ---------------------------------------------------------------------------
# 1B-i — LogPublisher.log_progress() vs log_prompt()
# ---------------------------------------------------------------------------


class TestLogPublisherLogProgress:
    """Verify log_progress returns type PROGRESS, log_prompt returns LOG."""

    def test_log_progress_type(self):
        from unstract.core.pubsub_helper import LogPublisher

        result = LogPublisher.log_progress(
            component={"tool_id": "t1"},
            level="INFO",
            state="TOOL_RUN",
            message="Extracting text...",
        )
        assert result["type"] == "PROGRESS"
        assert result["service"] == "prompt"
        assert result["message"] == "Extracting text..."
        assert result["component"] == {"tool_id": "t1"}
        assert "timestamp" in result

    def test_log_prompt_type_unchanged(self):
        from unstract.core.pubsub_helper import LogPublisher

        result = LogPublisher.log_prompt(
            component={"tool_id": "t1"},
            level="INFO",
            state="RUNNING",
            message="test",
        )
        assert result["type"] == "LOG"
        assert result["service"] == "prompt"

    def test_log_progress_has_all_fields(self):
        from unstract.core.pubsub_helper import LogPublisher

        result = LogPublisher.log_progress(
            component={"tool_id": "t1", "prompt_key": "pk"},
            level="ERROR",
            state="FAILED",
            message="boom",
        )
        assert result["level"] == "ERROR"
        assert result["state"] == "FAILED"
        assert result["component"]["prompt_key"] == "pk"


# ---------------------------------------------------------------------------
# 1B-ii — ExecutorToolShim progress publishing
# ---------------------------------------------------------------------------


class TestExecutorToolShimProgress:
    """Verify ExecutorToolShim publishes progress via LogPublisher."""

    @patch("executor.executor_tool_shim.LogPublisher")
    def test_stream_log_publishes_when_log_events_id_set(self, mock_lp):
        from executor.executor_tool_shim import ExecutorToolShim

        component = {"tool_id": "t1", "run_id": "r1"}
        shim = ExecutorToolShim(
            platform_api_key="sk-test",
            log_events_id="session-xyz",
            component=component,
        )
        shim.stream_log("Extracting...", level=LogLevel.INFO)

        mock_lp.log_progress.assert_called_once_with(
            component=component,
            level="INFO",
            state="TOOL_RUN",
            message="Extracting...",
        )
        mock_lp.publish.assert_called_once_with(
            channel_id="session-xyz",
            payload=mock_lp.log_progress.return_value,
        )

    @patch("executor.executor_tool_shim.LogPublisher")
    def test_stream_log_no_publish_without_log_events_id(self, mock_lp):
        from executor.executor_tool_shim import ExecutorToolShim

        shim = ExecutorToolShim(platform_api_key="sk-test")
        shim.stream_log("Hello", level=LogLevel.INFO)

        mock_lp.log_progress.assert_not_called()
        mock_lp.publish.assert_not_called()

    @patch("executor.executor_tool_shim.LogPublisher")
    def test_stream_log_empty_log_events_id_no_publish(self, mock_lp):
        from executor.executor_tool_shim import ExecutorToolShim

        shim = ExecutorToolShim(
            platform_api_key="sk-test", log_events_id=""
        )
        shim.stream_log("Hello", level=LogLevel.INFO)

        mock_lp.log_progress.assert_not_called()

    @patch("executor.executor_tool_shim.LogPublisher")
    def test_stream_log_swallows_publish_error(self, mock_lp):
        from executor.executor_tool_shim import ExecutorToolShim

        mock_lp.publish.side_effect = ConnectionError("AMQP down")
        shim = ExecutorToolShim(
            platform_api_key="sk-test",
            log_events_id="session-xyz",
            component={"tool_id": "t1"},
        )
        # Should NOT raise
        shim.stream_log("test", level=LogLevel.INFO)

    @patch("executor.executor_tool_shim.LogPublisher")
    def test_level_mapping(self, mock_lp):
        from executor.executor_tool_shim import ExecutorToolShim

        shim = ExecutorToolShim(
            platform_api_key="sk-test",
            log_events_id="s1",
            component={},
        )

        cases = [
            (LogLevel.DEBUG, "INFO"),
            (LogLevel.INFO, "INFO"),
            (LogLevel.WARN, "WARN"),
            (LogLevel.ERROR, "ERROR"),
            (LogLevel.FATAL, "ERROR"),
        ]
        for sdk_level, expected_wf_level in cases:
            mock_lp.reset_mock()
            shim.stream_log("msg", level=sdk_level)
            call_kwargs = mock_lp.log_progress.call_args
            assert call_kwargs.kwargs["level"] == expected_wf_level, (
                f"SDK {sdk_level} should map to {expected_wf_level}"
            )

    @patch("executor.executor_tool_shim.LogPublisher")
    def test_custom_stage_passed_through(self, mock_lp):
        from executor.executor_tool_shim import ExecutorToolShim

        shim = ExecutorToolShim(
            platform_api_key="sk-test",
            log_events_id="s1",
            component={},
        )
        shim.stream_log("msg", level=LogLevel.INFO, stage="INDEXING")
        call_kwargs = mock_lp.log_progress.call_args
        assert call_kwargs.kwargs["state"] == "INDEXING"


# ---------------------------------------------------------------------------
# 1C — Component dict building in execute_extraction
# ---------------------------------------------------------------------------


class TestExecuteExtractionComponentDict:
    """Verify component dict is built from executor_params."""

    @patch("executor.tasks.ExecutionOrchestrator")
    def test_component_dict_built_when_log_events_id_present(
        self, mock_orch_cls
    ):
        mock_orch = MagicMock()
        mock_orch.execute.return_value = MagicMock(
            success=True, to_dict=lambda: {"success": True}
        )
        mock_orch_cls.return_value = mock_orch

        from executor.tasks import execute_extraction

        payload = {
            "executor_name": "legacy",
            "operation": "extract",
            "run_id": "r1",
            "execution_source": "ide",
            "log_events_id": "session-abc",
            "executor_params": {
                "tool_id": "tool-123",
                "file_name": "invoice.pdf",
            },
        }
        execute_extraction(payload)

        # Verify the context passed to orchestrator has _log_component
        ctx = mock_orch.execute.call_args[0][0]
        assert ctx._log_component == {
            "tool_id": "tool-123",
            "run_id": "r1",
            "doc_name": "invoice.pdf",
            "operation": "extract",
        }

    @patch("executor.tasks.ExecutionOrchestrator")
    def test_component_dict_empty_when_no_log_events_id(
        self, mock_orch_cls
    ):
        mock_orch = MagicMock()
        mock_orch.execute.return_value = MagicMock(
            success=True, to_dict=lambda: {"success": True}
        )
        mock_orch_cls.return_value = mock_orch

        from executor.tasks import execute_extraction

        payload = {
            "executor_name": "legacy",
            "operation": "extract",
            "run_id": "r1",
            "execution_source": "ide",
            "executor_params": {},
        }
        execute_extraction(payload)

        ctx = mock_orch.execute.call_args[0][0]
        assert ctx._log_component == {}


# ---------------------------------------------------------------------------
# 1D — LegacyExecutor passes log info to shim
# ---------------------------------------------------------------------------


class TestLegacyExecutorLogPassthrough:
    """Verify LegacyExecutor passes log_events_id and component to shim."""

    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_extract_passes_log_info_to_shim(
        self, mock_shim_cls, mock_x2text, mock_fs
    ):
        from executor.executors.legacy_executor import LegacyExecutor
        from unstract.sdk1.execution.registry import ExecutorRegistry

        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry._registry["legacy"] = LegacyExecutor

        mock_shim = MagicMock()
        mock_shim_cls.return_value = mock_shim
        mock_x2t = MagicMock()
        mock_x2t.process.return_value = MagicMock(
            extracted_text="hello"
        )
        mock_x2text.return_value = mock_x2t

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="r1",
            execution_source="ide",
            log_events_id="session-abc",
            executor_params={
                "x2text_instance_id": "x2t-1",
                "file_path": "/tmp/test.pdf",
                "platform_api_key": "sk-test",
            },
        )
        ctx._log_component = {"tool_id": "t1", "run_id": "r1", "doc_name": "test.pdf"}

        executor = LegacyExecutor()
        result = executor.execute(ctx)

        assert result.success
        mock_shim_cls.assert_called_once_with(
            platform_api_key="sk-test",
            log_events_id="session-abc",
            component={"tool_id": "t1", "run_id": "r1", "doc_name": "test.pdf"},
        )

    @patch("executor.executors.legacy_executor.FileUtils.get_fs_instance")
    @patch("executor.executors.legacy_executor.X2Text")
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_extract_no_log_info_when_absent(
        self, mock_shim_cls, mock_x2text, mock_fs
    ):
        from executor.executors.legacy_executor import LegacyExecutor
        from unstract.sdk1.execution.registry import ExecutorRegistry

        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry._registry["legacy"] = LegacyExecutor

        mock_shim = MagicMock()
        mock_shim_cls.return_value = mock_shim
        mock_x2t = MagicMock()
        mock_x2t.process.return_value = MagicMock(
            extracted_text="hello"
        )
        mock_x2text.return_value = mock_x2t

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id="r1",
            execution_source="tool",
            executor_params={
                "x2text_instance_id": "x2t-1",
                "file_path": "/tmp/test.pdf",
                "platform_api_key": "sk-test",
            },
        )

        executor = LegacyExecutor()
        result = executor.execute(ctx)

        assert result.success
        mock_shim_cls.assert_called_once_with(
            platform_api_key="sk-test",
            log_events_id="",
            component={},
        )

    @patch(
        "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
    )
    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    def test_answer_prompt_enriches_component_with_prompt_key(
        self, mock_shim_cls, mock_prompt_deps
    ):
        """Verify per-prompt shim includes prompt_key in component."""
        from executor.executors.legacy_executor import LegacyExecutor
        from unstract.sdk1.execution.registry import ExecutorRegistry

        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry._registry["legacy"] = LegacyExecutor

        mock_shim = MagicMock()
        mock_shim_cls.return_value = mock_shim

        # Mock prompt deps
        MockAnswerPromptService = MagicMock()
        MockAnswerPromptService.extract_variable.return_value = "prompt text"
        MockRetrievalService = MagicMock()
        MockVariableReplacementService = MagicMock()
        MockVariableReplacementService.is_variables_present.return_value = (
            False
        )
        MockIndex = MagicMock()
        MockLLM = MagicMock()
        MockEmbeddingCompat = MagicMock()
        MockVectorDB = MagicMock()

        mock_prompt_deps.return_value = (
            MockAnswerPromptService,
            MockRetrievalService,
            MockVariableReplacementService,
            MockIndex,
            MockLLM,
            MockEmbeddingCompat,
            MockVectorDB,
        )

        ctx = ExecutionContext(
            executor_name="legacy",
            operation="answer_prompt",
            run_id="r1",
            execution_source="ide",
            log_events_id="session-abc",
            executor_params={
                "tool_id": "t1",
                "outputs": [
                    {
                        "name": "invoice_number",
                        "prompt": "What is the invoice number?",
                        "chunk-size": 0,
                        "type": "text",
                        "retrieval-strategy": "simple",
                        "vector-db": "vdb1",
                        "embedding": "emb1",
                        "x2text_adapter": "x2t1",
                        "chunk-overlap": 0,
                        "llm": "llm1",
                    },
                ],
                "tool_settings": {},
                "PLATFORM_SERVICE_API_KEY": "sk-test",
            },
        )
        ctx._log_component = {
            "tool_id": "t1",
            "run_id": "r1",
            "doc_name": "test.pdf",
        }

        # Mock IndexingUtils
        with patch(
            "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
            return_value="doc-id-1",
        ):
            executor = LegacyExecutor()
            # The handler will try retrieval which we need to mock
            MockRetrievalService.retrieve_complete_context.return_value = [
                "context"
            ]
            MockAnswerPromptService.construct_and_run_prompt.return_value = (
                "INV-001"
            )

            executor.execute(ctx)

        # Check that shim was created with prompt_key in component
        shim_call = mock_shim_cls.call_args
        assert shim_call.kwargs["component"]["prompt_key"] == "invoice_number"
        assert shim_call.kwargs["log_events_id"] == "session-abc"
