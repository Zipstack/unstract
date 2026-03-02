"""Phase 6C Sanity — Highlight data as cross-cutting plugin.

Verifies:
1. run_completion() passes process_text to llm.complete()
2. run_completion() with process_text=None (default) works as before
3. construct_and_run_prompt() passes process_text through to run_completion()
4. _handle_answer_prompt() initializes highlight plugin when enabled + available
5. _handle_answer_prompt() skips highlight when plugin not installed
6. _handle_answer_prompt() skips highlight when enable_highlight=False
7. Highlight metadata populated when plugin provides data via process_text
"""

from unittest.mock import MagicMock, call, patch

import pytest
from executor.executors.answer_prompt import AnswerPromptService
from executor.executors.constants import PromptServiceConstants as PSKeys


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_llm():
    """Create a mock LLM that returns a realistic completion dict."""
    llm = MagicMock()
    llm.complete.return_value = {
        PSKeys.RESPONSE: MagicMock(text="42"),
        PSKeys.HIGHLIGHT_DATA: [{"line": 1}],
        PSKeys.CONFIDENCE_DATA: {"score": 0.95},
        PSKeys.WORD_CONFIDENCE_DATA: {"words": []},
        PSKeys.LINE_NUMBERS: [1, 2],
        PSKeys.WHISPER_HASH: "abc123",
    }
    return llm


@pytest.fixture()
def mock_llm_no_highlight():
    """Create a mock LLM that returns completion without highlight data."""
    llm = MagicMock()
    llm.complete.return_value = {
        PSKeys.RESPONSE: MagicMock(text="answer"),
        PSKeys.HIGHLIGHT_DATA: [],
        PSKeys.LINE_NUMBERS: [],
        PSKeys.WHISPER_HASH: "",
    }
    return llm


# ---------------------------------------------------------------------------
# 1. run_completion() passes process_text to llm.complete()
# ---------------------------------------------------------------------------

class TestRunCompletionProcessText:
    def test_process_text_passed_to_llm_complete(self, mock_llm):
        """process_text callback is forwarded to llm.complete()."""
        callback = MagicMock(name="highlight_run")
        AnswerPromptService.run_completion(
            llm=mock_llm,
            prompt="test prompt",
            process_text=callback,
        )
        mock_llm.complete.assert_called_once()
        call_kwargs = mock_llm.complete.call_args
        assert call_kwargs.kwargs.get("process_text") is callback or \
            call_kwargs[1].get("process_text") is callback

    def test_process_text_none_by_default(self, mock_llm):
        """When process_text not provided, None is passed to llm.complete()."""
        AnswerPromptService.run_completion(
            llm=mock_llm,
            prompt="test prompt",
        )
        call_kwargs = mock_llm.complete.call_args
        # Check both positional and keyword args
        pt = call_kwargs.kwargs.get("process_text", "MISSING")
        if pt == "MISSING":
            # Might be positional
            pt = call_kwargs[1].get("process_text")
        assert pt is None

    def test_process_text_none_explicit(self, mock_llm):
        """Explicit process_text=None works as before."""
        answer = AnswerPromptService.run_completion(
            llm=mock_llm,
            prompt="test prompt",
            process_text=None,
        )
        assert answer == "42"


# ---------------------------------------------------------------------------
# 2. run_completion() populates metadata from completion dict
# ---------------------------------------------------------------------------

class TestRunCompletionMetadata:
    def test_highlight_metadata_populated_with_process_text(self, mock_llm):
        """When process_text is provided and LLM returns highlight data,
        metadata is populated correctly."""
        callback = MagicMock(name="highlight_run")
        metadata: dict = {}
        AnswerPromptService.run_completion(
            llm=mock_llm,
            prompt="test",
            metadata=metadata,
            prompt_key="field1",
            enable_highlight=True,
            enable_word_confidence=True,
            process_text=callback,
        )
        assert metadata[PSKeys.HIGHLIGHT_DATA]["field1"] == [{"line": 1}]
        assert metadata[PSKeys.CONFIDENCE_DATA]["field1"] == {"score": 0.95}
        assert metadata[PSKeys.WORD_CONFIDENCE_DATA]["field1"] == {"words": []}
        assert metadata[PSKeys.LINE_NUMBERS]["field1"] == [1, 2]
        assert metadata[PSKeys.WHISPER_HASH] == "abc123"

    def test_highlight_metadata_empty_without_process_text(
        self, mock_llm_no_highlight
    ):
        """Without process_text, highlight data is empty but no error."""
        metadata: dict = {}
        AnswerPromptService.run_completion(
            llm=mock_llm_no_highlight,
            prompt="test",
            metadata=metadata,
            prompt_key="field1",
            enable_highlight=True,
            process_text=None,
        )
        assert metadata[PSKeys.HIGHLIGHT_DATA]["field1"] == []
        assert metadata[PSKeys.LINE_NUMBERS]["field1"] == []


# ---------------------------------------------------------------------------
# 3. construct_and_run_prompt() passes process_text through
# ---------------------------------------------------------------------------

class TestConstructAndRunPromptProcessText:
    def test_process_text_forwarded(self, mock_llm):
        """construct_and_run_prompt passes process_text to run_completion."""
        callback = MagicMock(name="highlight_run")
        tool_settings = {
            PSKeys.PREAMBLE: "",
            PSKeys.POSTAMBLE: "",
            PSKeys.GRAMMAR: [],
            PSKeys.ENABLE_HIGHLIGHT: True,
        }
        output = {
            PSKeys.NAME: "field1",
            PSKeys.PROMPT: "What is the value?",
            PSKeys.PROMPTX: "What is the value?",
            PSKeys.TYPE: PSKeys.TEXT,
        }
        answer = AnswerPromptService.construct_and_run_prompt(
            tool_settings=tool_settings,
            output=output,
            llm=mock_llm,
            context="some context",
            prompt=PSKeys.PROMPTX,
            metadata={},
            process_text=callback,
        )
        # Verify callback was passed to llm.complete
        call_kwargs = mock_llm.complete.call_args
        pt = call_kwargs.kwargs.get("process_text")
        if pt is None:
            pt = call_kwargs[1].get("process_text")
        assert pt is callback
        assert answer == "42"

    def test_process_text_none_default(self, mock_llm):
        """construct_and_run_prompt defaults process_text to None."""
        tool_settings = {
            PSKeys.PREAMBLE: "",
            PSKeys.POSTAMBLE: "",
            PSKeys.GRAMMAR: [],
        }
        output = {
            PSKeys.NAME: "field1",
            PSKeys.PROMPT: "What?",
            PSKeys.PROMPTX: "What?",
            PSKeys.TYPE: PSKeys.TEXT,
        }
        AnswerPromptService.construct_and_run_prompt(
            tool_settings=tool_settings,
            output=output,
            llm=mock_llm,
            context="ctx",
            prompt=PSKeys.PROMPTX,
            metadata={},
        )
        call_kwargs = mock_llm.complete.call_args
        pt = call_kwargs.kwargs.get("process_text")
        if pt is None and "process_text" not in (call_kwargs.kwargs or {}):
            pt = call_kwargs[1].get("process_text")
        assert pt is None


# ---------------------------------------------------------------------------
# 4. _handle_answer_prompt() initializes highlight plugin
# ---------------------------------------------------------------------------

class TestHandleAnswerPromptHighlight:
    """Test highlight plugin integration in LegacyExecutor._handle_answer_prompt."""

    def _make_context(self, enable_highlight=False):
        """Build a minimal ExecutionContext for answer_prompt."""
        from unstract.sdk1.execution.context import ExecutionContext

        prompt_output = {
            PSKeys.NAME: "field1",
            PSKeys.PROMPT: "What is X?",
            PSKeys.PROMPTX: "What is X?",
            PSKeys.TYPE: PSKeys.TEXT,
            PSKeys.CHUNK_SIZE: 0,
            PSKeys.CHUNK_OVERLAP: 0,
            PSKeys.LLM: "llm-123",
            PSKeys.EMBEDDING: "emb-123",
            PSKeys.VECTOR_DB: "vdb-123",
            PSKeys.X2TEXT_ADAPTER: "x2t-123",
            PSKeys.RETRIEVAL_STRATEGY: "simple",
        }
        return ExecutionContext(
            executor_name="legacy",
            operation="answer_prompt",
            run_id="run-001",
            execution_source="ide",
            organization_id="org-1",
            executor_params={
                PSKeys.TOOL_SETTINGS: {
                    PSKeys.PREAMBLE: "",
                    PSKeys.POSTAMBLE: "",
                    PSKeys.GRAMMAR: [],
                    PSKeys.ENABLE_HIGHLIGHT: enable_highlight,
                },
                PSKeys.OUTPUTS: [prompt_output],
                PSKeys.TOOL_ID: "tool-1",
                PSKeys.FILE_HASH: "hash123",
                PSKeys.FILE_PATH: "/data/doc.txt",
                PSKeys.FILE_NAME: "doc.txt",
                PSKeys.PLATFORM_SERVICE_API_KEY: "key-123",
            },
        )

    def _get_executor(self):
        from executor.executors.legacy_executor import LegacyExecutor
        from unstract.sdk1.execution.registry import ExecutorRegistry

        ExecutorRegistry.clear()
        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)
        return ExecutorRegistry.get("legacy")

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_highlight_plugin_initialized_when_enabled(
        self, mock_index_key, mock_shim_cls
    ):
        """When enable_highlight=True and plugin available, highlight is used."""
        mock_shim_cls.return_value = MagicMock()

        # Mock highlight plugin
        mock_highlight_cls = MagicMock()
        mock_highlight_instance = MagicMock()
        mock_highlight_cls.return_value = mock_highlight_instance

        # Mock LLM
        mock_llm = MagicMock()
        mock_llm.complete.return_value = {
            PSKeys.RESPONSE: MagicMock(text="result"),
            PSKeys.HIGHLIGHT_DATA: [{"line": 5}],
            PSKeys.CONFIDENCE_DATA: {"score": 0.9},
            PSKeys.LINE_NUMBERS: [5],
            PSKeys.WHISPER_HASH: "hash1",
        }
        mock_llm.get_usage_reason.return_value = "extraction"
        mock_llm.get_metrics.return_value = {}

        mock_fs = MagicMock()
        mock_llm_cls = MagicMock(return_value=mock_llm)

        executor = self._get_executor()
        ctx = self._make_context(enable_highlight=True)

        with (
            patch.object(
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
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                return_value=mock_highlight_cls,
            ),
            patch(
                "executor.executors.file_utils.FileUtils.get_fs_instance",
                return_value=mock_fs,
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # Verify highlight plugin was instantiated
        mock_highlight_cls.assert_called_once_with(
            file_path="/data/doc.txt",
            fs_instance=mock_fs,
            execution_source="ide",
        )
        # Verify process_text was the highlight instance's run method
        llm_complete_call = mock_llm.complete.call_args
        assert llm_complete_call.kwargs.get("process_text") is \
            mock_highlight_instance.run

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_highlight_skipped_when_plugin_not_installed(
        self, mock_index_key, mock_shim_cls
    ):
        """When enable_highlight=True but plugin not installed, process_text=None."""
        mock_shim = MagicMock()
        mock_shim_cls.return_value = mock_shim

        mock_llm = MagicMock()
        mock_llm.complete.return_value = {
            PSKeys.RESPONSE: MagicMock(text="result"),
            PSKeys.HIGHLIGHT_DATA: [],
            PSKeys.LINE_NUMBERS: [],
            PSKeys.WHISPER_HASH: "",
        }
        mock_llm.get_usage_reason.return_value = "extraction"
        mock_llm.get_metrics.return_value = {}

        executor = self._get_executor()
        ctx = self._make_context(enable_highlight=True)

        mock_llm_cls = MagicMock(return_value=mock_llm)
        with (
            patch.object(
                executor, "_get_prompt_deps",
                return_value=(
                    AnswerPromptService,
                    MagicMock(
                        retrieve_complete_context=MagicMock(
                            return_value=["chunk"]
                        )
                    ),
                    MagicMock(
                        is_variables_present=MagicMock(return_value=False)
                    ),
                    None,
                    mock_llm_cls,
                    MagicMock(),
                    MagicMock(),
                ),
            ),
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                return_value=None,  # Plugin not installed
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # process_text should be None since plugin not available
        llm_complete_call = mock_llm.complete.call_args
        assert llm_complete_call.kwargs.get("process_text") is None

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_highlight_skipped_when_disabled(
        self, mock_index_key, mock_shim_cls
    ):
        """When enable_highlight=False, plugin loader is not even called."""
        mock_shim = MagicMock()
        mock_shim_cls.return_value = mock_shim

        mock_llm = MagicMock()
        mock_llm.complete.return_value = {
            PSKeys.RESPONSE: MagicMock(text="result"),
            PSKeys.HIGHLIGHT_DATA: [],
            PSKeys.LINE_NUMBERS: [],
            PSKeys.WHISPER_HASH: "",
        }
        mock_llm.get_usage_reason.return_value = "extraction"
        mock_llm.get_metrics.return_value = {}

        executor = self._get_executor()
        ctx = self._make_context(enable_highlight=False)

        mock_llm_cls = MagicMock(return_value=mock_llm)
        with (
            patch.object(
                executor, "_get_prompt_deps",
                return_value=(
                    AnswerPromptService,
                    MagicMock(
                        retrieve_complete_context=MagicMock(
                            return_value=["chunk"]
                        )
                    ),
                    MagicMock(
                        is_variables_present=MagicMock(return_value=False)
                    ),
                    None,
                    mock_llm_cls,
                    MagicMock(),
                    MagicMock(),
                ),
            ),
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
            ) as mock_plugin_get,
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # Plugin loader should NOT have been called
        mock_plugin_get.assert_not_called()
        # process_text should be None
        llm_complete_call = mock_llm.complete.call_args
        assert llm_complete_call.kwargs.get("process_text") is None


# ---------------------------------------------------------------------------
# 5. Multiple prompts share same highlight instance
# ---------------------------------------------------------------------------

class TestHighlightMultiplePrompts:
    """Verify that one highlight instance is shared across all prompts."""

    def _make_multi_prompt_context(self):
        from unstract.sdk1.execution.context import ExecutionContext

        prompts = []
        for name in ["field1", "field2", "field3"]:
            prompts.append({
                PSKeys.NAME: name,
                PSKeys.PROMPT: f"What is {name}?",
                PSKeys.PROMPTX: f"What is {name}?",
                PSKeys.TYPE: PSKeys.TEXT,
                PSKeys.CHUNK_SIZE: 0,
                PSKeys.CHUNK_OVERLAP: 0,
                PSKeys.LLM: "llm-123",
                PSKeys.EMBEDDING: "emb-123",
                PSKeys.VECTOR_DB: "vdb-123",
                PSKeys.X2TEXT_ADAPTER: "x2t-123",
                PSKeys.RETRIEVAL_STRATEGY: "simple",
            })
        return ExecutionContext(
            executor_name="legacy",
            operation="answer_prompt",
            run_id="run-002",
            execution_source="tool",
            organization_id="org-1",
            executor_params={
                PSKeys.TOOL_SETTINGS: {
                    PSKeys.PREAMBLE: "",
                    PSKeys.POSTAMBLE: "",
                    PSKeys.GRAMMAR: [],
                    PSKeys.ENABLE_HIGHLIGHT: True,
                },
                PSKeys.OUTPUTS: prompts,
                PSKeys.TOOL_ID: "tool-1",
                PSKeys.FILE_HASH: "hash123",
                PSKeys.FILE_PATH: "/data/doc.txt",
                PSKeys.FILE_NAME: "doc.txt",
                PSKeys.PLATFORM_SERVICE_API_KEY: "key-123",
            },
        )

    @patch("executor.executors.legacy_executor.ExecutorToolShim")
    @patch("unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
           return_value="doc-id-1")
    def test_single_highlight_instance_for_all_prompts(
        self, mock_index_key, mock_shim_cls
    ):
        """One highlight instance is created and reused for all prompts."""
        mock_shim_cls.return_value = MagicMock()

        mock_highlight_cls = MagicMock()
        mock_highlight_instance = MagicMock()
        mock_highlight_cls.return_value = mock_highlight_instance

        mock_llm = MagicMock()
        mock_llm.complete.return_value = {
            PSKeys.RESPONSE: MagicMock(text="val"),
            PSKeys.HIGHLIGHT_DATA: [],
            PSKeys.LINE_NUMBERS: [],
            PSKeys.WHISPER_HASH: "",
        }
        mock_llm.get_usage_reason.return_value = "extraction"
        mock_llm.get_metrics.return_value = {}

        from executor.executors.legacy_executor import LegacyExecutor
        from unstract.sdk1.execution.registry import ExecutorRegistry

        ExecutorRegistry.clear()
        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)
        executor = ExecutorRegistry.get("legacy")
        ctx = self._make_multi_prompt_context()

        mock_llm_cls = MagicMock(return_value=mock_llm)
        with (
            patch.object(
                executor, "_get_prompt_deps",
                return_value=(
                    AnswerPromptService,
                    MagicMock(
                        retrieve_complete_context=MagicMock(
                            return_value=["chunk"]
                        )
                    ),
                    MagicMock(
                        is_variables_present=MagicMock(return_value=False)
                    ),
                    None,
                    mock_llm_cls,
                    MagicMock(),
                    MagicMock(),
                ),
            ),
            patch(
                "executor.executors.plugins.loader.ExecutorPluginLoader.get",
                return_value=mock_highlight_cls,
            ),
            patch(
                "executor.executors.file_utils.FileUtils.get_fs_instance",
                return_value=MagicMock(),
            ),
        ):
            result = executor._handle_answer_prompt(ctx)

        assert result.success
        # highlight_cls should be instantiated exactly ONCE
        assert mock_highlight_cls.call_count == 1
        # llm.complete should be called 3 times (once per prompt)
        assert mock_llm.complete.call_count == 3
        # Each call should use the same process_text
        for c in mock_llm.complete.call_args_list:
            assert c.kwargs.get("process_text") is mock_highlight_instance.run
