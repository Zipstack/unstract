"""Guardrail tests for flag-gated prompt-caching in answer_prompt.

When ``ENABLE_PROMPT_CACHING`` is on, ``construct_cached_prompt`` reorders the
prompt so the reused document context becomes a cacheable prefix (context
first) instead of a suffix (context last). These tests lock in that:

- the default (flag off) prompt is unchanged (context last),
- the cached variant is a pure *reorder* — every piece of the original prompt
  is preserved, only the context moves to the front,
- ``cache_prefix`` is exactly the context block (no per-prompt question), so
  it repeats byte-for-byte across prompts on the same document,
- the flag reads the env var and defaults off.

The executor package's ``__init__`` pulls the full celery stack, so we load the
module with stubbed parent packages — the methods under test are pure strings.
"""

import importlib
import os
import sys
import types

import pytest

_WORKERS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_answer_prompt():
    for pkg, rel in [("executor", "executor"), ("executor.executors", "executor/executors")]:
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            mod.__path__ = [os.path.join(_WORKERS, rel)]
            sys.modules[pkg] = mod
    return importlib.import_module("executor.executors.answer_prompt")


_mod = _load_answer_prompt()
A = _mod.AnswerPromptService

_ARGS = dict(
    preamble="You are an extractor.",
    prompt="What is the tenant name?",
    postamble="Answer concisely.",
    grammar_list=[],
    context="UNIT 101 John Smith $1,450\nUNIT 102 Maria Davis $1,525",
    platform_postamble="",
    word_confidence_postamble="",
    prompt_type="text",
)


def test_default_prompt_is_context_last():
    off = A.construct_prompt(**_ARGS)
    assert off.index("Question or Instruction") < off.index("UNIT 101")


def test_cached_prompt_is_context_first():
    prefix, volatile = A.construct_cached_prompt(**_ARGS)
    full = prefix + volatile
    assert full.index("UNIT 101") < full.index("Question or Instruction")


def test_cache_prefix_is_context_block_only():
    prefix, _volatile = A.construct_cached_prompt(**_ARGS)
    assert prefix.startswith("Context:")
    assert "UNIT 101" in prefix
    # The volatile per-prompt question must NOT leak into the cached prefix,
    # or the prefix would differ per prompt and never hit the cache.
    assert "Question or Instruction" not in prefix


def test_cached_variant_is_a_pure_reorder_no_content_lost():
    prefix, volatile = A.construct_cached_prompt(**_ARGS)
    full = prefix + volatile
    for piece in (
        "You are an extractor.",
        "Question or Instruction: What is the tenant name?",
        "Answer concisely.",
        "UNIT 101 John Smith $1,450",
        "Answer:",
    ):
        assert piece in full, f"missing from cached prompt: {piece!r}"


def test_flag_defaults_off_and_reads_env(monkeypatch):
    monkeypatch.delenv("ENABLE_PROMPT_CACHING", raising=False)
    assert _mod.is_prompt_caching_enabled() is False
    monkeypatch.setenv("ENABLE_PROMPT_CACHING", "true")
    assert _mod.is_prompt_caching_enabled() is True
    monkeypatch.setenv("ENABLE_PROMPT_CACHING", "false")
    assert _mod.is_prompt_caching_enabled() is False


# --- gate: only reorder into a cached prefix when the LLM actually caches -----


class _FakeLLM:
    """Minimal LLM stub exposing the SDK's caching-capability probe."""

    def __init__(self, active: bool):
        self._active = active

    def is_prompt_caching_active(self) -> bool:
        return self._active


class _LegacyLLM:
    """LLM stub without the capability probe (older SDK / mock)."""


def test_llm_caches_prompts_probe():
    assert A._llm_caches_prompts(_FakeLLM(True)) is True
    assert A._llm_caches_prompts(_FakeLLM(False)) is False
    # An LLM that doesn't expose the probe must default to "no caching".
    assert A._llm_caches_prompts(_LegacyLLM()) is False


def test_llm_caches_prompts_probe_swallows_errors():
    class _BoomLLM:
        def is_prompt_caching_active(self):
            raise RuntimeError("boom")

    assert A._llm_caches_prompts(_BoomLLM()) is False


def _run_and_capture(monkeypatch, llm):
    """Run construct_and_run_prompt with run_completion stubbed to capture args."""
    captured: dict = {}

    def _fake_run_completion(**kwargs):
        captured.update(kwargs)
        return "answer"

    monkeypatch.setattr(A, "run_completion", staticmethod(_fake_run_completion))

    tool_settings = {
        _mod.PSKeys.PREAMBLE: "You are an extractor.",
        _mod.PSKeys.POSTAMBLE: "Answer concisely.",
        _mod.PSKeys.GRAMMAR: [],
    }
    output = {
        "promptx": "What is the tenant name?",
        _mod.PSKeys.NAME: "q1",
        _mod.PSKeys.TYPE: "text",
    }
    A.construct_and_run_prompt(
        tool_settings=tool_settings,
        output=output,
        llm=llm,
        context="UNIT 101 John Smith $1,450",
        prompt="promptx",
        metadata={},
    )
    return captured, output


def test_supported_llm_reorders_and_sends_cache_prefix(monkeypatch):
    captured, output = _run_and_capture(monkeypatch, _FakeLLM(True))
    # Cached path: context-first prompt + a cache_prefix that is the context.
    assert captured["cache_prefix"] is not None
    assert captured["cache_prefix"].startswith("Context:")
    combined = output[_mod.PSKeys.COMBINED_PROMPT]
    assert combined.index("UNIT 101") < combined.index("Question or Instruction")


def test_unsupported_llm_keeps_original_order_and_no_cache_prefix(monkeypatch):
    # Global flag ON, but the LLM's provider/model does not support caching.
    monkeypatch.setenv("ENABLE_PROMPT_CACHING", "true")
    captured, output = _run_and_capture(monkeypatch, _FakeLLM(False))
    # No cache prefix, and the original context-last prompt order is preserved.
    assert captured["cache_prefix"] is None
    combined = output[_mod.PSKeys.COMBINED_PROMPT]
    assert combined.index("Question or Instruction") < combined.index("UNIT 101")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
