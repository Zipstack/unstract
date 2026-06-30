"""Tests for the single-pass extraction vision mode guard (Phase 9a).

Verifies that SinglePassExtractionExecutor rejects payloads containing
vision-enabled prompts, since single-pass merges all prompts into one
LLM call that cannot apply per-prompt vision modes.

The single_pass_extraction plugin is installed separately (cloud-only),
so we add its src directory to sys.path for testing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from executor.executors.constants import PromptServiceConstants as PSKeys

from unstract.sdk1.execution.context import ExecutionContext, Operation

# Add plugin src to path so we can import it
_plugin_src = str(
    Path(__file__).resolve().parent.parent / "plugins" / "single_pass_extraction" / "src"
)
if _plugin_src not in sys.path:
    sys.path.insert(0, _plugin_src)


def _make_output(
    name: str = "field_a",
    extraction_inputs: str = "text",
) -> dict:
    """Build a minimal prompt output dict for single-pass."""
    return {
        PSKeys.NAME: name,
        PSKeys.PROMPT: "What is the value?",
        PSKeys.TYPE: "text",
        PSKeys.CHUNK_SIZE: 0,
        PSKeys.CHUNK_OVERLAP: 0,
        PSKeys.RETRIEVAL_STRATEGY: "simple",
        PSKeys.LLM: "llm-1",
        PSKeys.EMBEDDING: "emb-1",
        PSKeys.VECTOR_DB: "vdb-1",
        PSKeys.X2TEXT_ADAPTER: "x2t-1",
        PSKeys.SIMILARITY_TOP_K: 5,
        PSKeys.EXTRACTION_INPUTS: extraction_inputs,
    }


def _make_context(outputs: list[dict]) -> ExecutionContext:
    """Build an ExecutionContext for single-pass extraction."""
    params = {
        PSKeys.OUTPUTS: outputs,
        PSKeys.TOOL_SETTINGS: {PSKeys.LLM: "llm-1"},
        PSKeys.TOOL_ID: "tool-1",
        PSKeys.FILE_PATH: "/data/doc.txt",
        PSKeys.FILE_NAME: "doc.txt",
        PSKeys.EXECUTION_SOURCE: "tool",
        PSKeys.CUSTOM_DATA: {},
        PSKeys.PLATFORM_SERVICE_API_KEY: "pk-test",
    }
    return ExecutionContext(
        executor_name="single_pass_extraction",
        operation=Operation.SINGLE_PASS_EXTRACTION.value,
        executor_params=params,
        run_id="run-1",
        execution_source="tool",
    )


class TestSinglePassVisionGuard:
    """Single-pass extraction must reject vision-enabled prompts."""

    def test_text_only_prompts_pass_guard(self):
        """Text-only prompts should not trigger the guard."""
        from single_pass_extraction.executor import SinglePassExtractionExecutor

        executor = SinglePassExtractionExecutor()
        ctx = _make_context([
            _make_output("field_a", "text"),
            _make_output("field_b", "text"),
        ])

        # The guard only checks vision; execution will fail later on LLM init.
        # We just need to verify the guard itself doesn't block text-only.
        result = executor.execute(ctx)
        # It should NOT fail with the vision guard message
        if not result.success:
            assert "vision" not in result.error.lower()

    def test_image_only_prompt_triggers_guard(self):
        """A prompt with extraction_inputs='image' should be rejected."""
        from single_pass_extraction.executor import SinglePassExtractionExecutor

        executor = SinglePassExtractionExecutor()
        ctx = _make_context([
            _make_output("field_a", "image"),
        ])
        result = executor.execute(ctx)
        assert not result.success
        assert "vision" in result.error.lower()
        assert "field_a" in result.error

    def test_both_mode_prompt_triggers_guard(self):
        """A prompt with extraction_inputs='both' should be rejected."""
        from single_pass_extraction.executor import SinglePassExtractionExecutor

        executor = SinglePassExtractionExecutor()
        ctx = _make_context([
            _make_output("field_a", "both"),
        ])
        result = executor.execute(ctx)
        assert not result.success
        assert "vision" in result.error.lower()
        assert "field_a" in result.error

    def test_mixed_prompts_triggers_guard(self):
        """If ANY prompt has vision, the guard should reject."""
        from single_pass_extraction.executor import SinglePassExtractionExecutor

        executor = SinglePassExtractionExecutor()
        ctx = _make_context([
            _make_output("text_field", "text"),
            _make_output("vision_field", "image"),
        ])
        result = executor.execute(ctx)
        assert not result.success
        assert "vision_field" in result.error
        assert "text_field" not in result.error

    def test_missing_extraction_inputs_defaults_to_text(self):
        """Prompts without extraction_inputs field should default to text."""
        from single_pass_extraction.executor import SinglePassExtractionExecutor

        executor = SinglePassExtractionExecutor()
        output = _make_output("field_a", "text")
        del output[PSKeys.EXTRACTION_INPUTS]
        ctx = _make_context([output])

        result = executor.execute(ctx)
        # Should not fail with vision guard message
        if not result.success:
            assert "vision" not in result.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
