"""Guardrail tests for flag-gated prompt-caching in answer_prompt.

When ``ENABLE_PROMPT_CACHING`` is on, ``construct_cached_prompt`` reorders the
prompt so the reused document context becomes a cacheable prefix (context
first) instead of a suffix (context last). These tests lock in that:

- the default (flag off) prompt is unchanged (context last),
- the cached variant is a pure *reorder* — every piece of the original prompt
  is preserved, only the context moves to the front,
- ``cache_prefix`` is exactly the context block (no per-prompt question), so
  it repeats byte-for-byte across prompts on the same document,
- the reorder only happens when the selected LLM actually caches
  (``is_prompt_caching_active()``); unsupported LLMs keep the original order.

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
    """Import answer_prompt without triggering the executor package's celery stack.

    The real ``executor`` / ``executor.executors`` package ``__init__``s pull the
    full celery worker stack, so we temporarily register lightweight namespace
    stubs pointing at the real source dirs, import the module, then remove any
    stub we added. The imported module (and its already-resolved ``constants`` /
    ``exceptions`` imports) stay cached under their own names, so the stubs are
    unneeded afterwards — and removing them keeps ``sys.modules`` clean for other
    tests in the same process instead of leaving synthetic packages behind.
    """
    injected = []
    for pkg, rel in [
        ("executor", "executor"),
        ("executor.executors", "executor/executors"),
    ]:
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            mod.__path__ = [os.path.join(_WORKERS, rel)]
            sys.modules[pkg] = mod
            injected.append(pkg)
    try:
        return importlib.import_module("executor.executors.answer_prompt")
    finally:
        for pkg in injected:
            sys.modules.pop(pkg, None)


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


# --- shared postamble formatting (cached and uncached must not diverge) ------


def test_prepare_postambles_applies_json_and_platform_formatting():
    json_postamble = os.environ.get(
        _mod.PSKeys.JSON_POSTAMBLE, _mod.PSKeys.DEFAULT_JSON_POSTAMBLE
    )
    post, plat = A._prepare_postambles("BASE", "PLATFORM", "WORDCONF", _mod.PSKeys.JSON)
    assert post == f"BASE\n{json_postamble}"
    assert plat == "PLATFORM\n\nWORDCONF\n\n"


def test_prepare_postambles_noop_for_text_without_platform():
    post, plat = A._prepare_postambles("BASE", "", "", "text")
    assert post == "BASE"
    assert plat == ""


def test_cached_and_uncached_share_postamble_formatting():
    """Both builders route postambles through the shared helper, so a JSON +
    platform postamble is formatted identically — guards against silent
    divergence between cached and non-cached prompts (breaks A/B comparison)."""
    args = dict(_ARGS)
    args.update(
        prompt_type=_mod.PSKeys.JSON,
        postamble="BASE_POST",
        platform_postamble="PLATFORM",
        word_confidence_postamble="WORDCONF",
    )
    flat = A.construct_prompt(**args)
    prefix, volatile = A.construct_cached_prompt(**args)
    cached = prefix + volatile
    json_postamble = os.environ.get(
        _mod.PSKeys.JSON_POSTAMBLE, _mod.PSKeys.DEFAULT_JSON_POSTAMBLE
    )
    for piece in ("BASE_POST", "PLATFORM", "WORDCONF", json_postamble):
        assert piece in flat, f"missing from construct_prompt: {piece!r}"
        assert piece in cached, f"missing from construct_cached_prompt: {piece!r}"


def test_signature_context_lands_in_cached_prefix_and_matches_uncached():
    """LLMWhisperer ``document_insights`` signature metadata is per-document,
    so the cached builder must place it inside the reusable context prefix
    (not the volatile question) and both builders must emit the same block.
    """
    args = dict(_ARGS)
    args["signature_metadata"] = {
        "0": [{"name": "Mr Dagan", "type": "signature", "desc": "Director"}]
    }
    flat = A.construct_prompt(**args)
    prefix, volatile = A.construct_cached_prompt(**args)
    for piece in ("[Document Signature Information]", "Page 1: Mr Dagan (signature)"):
        assert piece in flat, f"missing from construct_prompt: {piece!r}"
        assert piece in prefix, f"missing from cache_prefix: {piece!r}"
        assert piece not in volatile, f"signature block leaked into volatile: {piece!r}"
    # Signature block sits inside the context delimiters in both variants.
    for text in (flat, prefix):
        assert text.index("UNIT 101") < text.index("[Document Signature Information]")
        assert text.index("[Document Signature Information]") < text.index(
            "-----------------"
        )


# NOTE: the ENABLE_PROMPT_CACHING env-var master switch is owned by the SDK
# (``unstract.sdk1.llm.is_prompt_caching_enabled``) and covered by its tests;
# answer_prompt gates purely on the LLM's ``is_prompt_caching_active()`` probe
# (see ``_llm_caches_prompts`` tests below), so there is no local env flag to
# test here.


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
