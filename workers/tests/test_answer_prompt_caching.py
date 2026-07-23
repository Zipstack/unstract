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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
