"""Tests for opt-in provider prompt caching.

Covers the two halves of the feature:

1. Adapter ``validate()`` (Anthropic + Bedrock-Anthropic) carries the
   ``enable_prompt_caching`` control flag through on the validated dict, but
   never leaks it into the LiteLLM completion kwargs Pydantic validates.
2. ``LLM._build_messages()`` tags only the stable system prompt with
   ``cache_control`` when caching is enabled, and leaves the string form
   untouched otherwise.
"""

from typing import Any

import pytest
from unstract.sdk1.adapters.base1 import (
    AnthropicLLMParameters,
    AWSBedrockLLMParameters,
)

# ── validate(): flag carried through, absent by default ─────────────────────

VALIDATE_CASES = [
    ("anthropic", AnthropicLLMParameters, "claude-opus-4-8", {"api_key": "k"}),
    (
        "bedrock",
        AWSBedrockLLMParameters,
        "anthropic.claude-opus-4-8-20260101-v1:0",
        {"aws_region_name": "us-east-1"},
    ),
]


@pytest.mark.parametrize(
    "name,cls,model,extra", VALIDATE_CASES, ids=[c[0] for c in VALIDATE_CASES]
)
def test_validate_defaults_prompt_caching_off(
    name: str, cls: type, model: str, extra: dict[str, Any]
) -> None:
    result = cls.validate({"model": model, **extra})
    assert result["enable_prompt_caching"] is False


@pytest.mark.parametrize(
    "name,cls,model,extra", VALIDATE_CASES, ids=[c[0] for c in VALIDATE_CASES]
)
def test_validate_carries_prompt_caching_flag(
    name: str, cls: type, model: str, extra: dict[str, Any]
) -> None:
    result = cls.validate({"model": model, "enable_prompt_caching": True, **extra})
    assert result["enable_prompt_caching"] is True


@pytest.mark.parametrize(
    "name,cls,model,extra", VALIDATE_CASES, ids=[c[0] for c in VALIDATE_CASES]
)
def test_validate_is_idempotent_on_prompt_caching(
    name: str, cls: type, model: str, extra: dict[str, Any]
) -> None:
    """Re-validating a validated dict must preserve the flag (round-trip)."""
    once = cls.validate({"model": model, "enable_prompt_caching": True, **extra})
    twice = cls.validate({**once})
    assert twice["enable_prompt_caching"] is True


# ── _build_messages(): cache_control only on the system prefix ──────────────


class _StubAdapter:
    def __init__(self, provider: str) -> None:
        self._provider = provider

    def get_provider(self) -> str:
        return self._provider


class _StubLLM:
    """Bind the real caching helpers to a stub carrying just the state they read."""

    from unstract.sdk1.llm import LLM

    _build_messages = LLM._build_messages
    _prompt_caching_active = LLM._prompt_caching_active
    is_prompt_caching_active = LLM.is_prompt_caching_active
    _PROMPT_CACHE_PROVIDERS = LLM._PROMPT_CACHE_PROVIDERS
    _BEDROCK_CACHE_MODEL_MARKERS = LLM._BEDROCK_CACHE_MODEL_MARKERS

    def __init__(
        self,
        system_prompt: str,
        enable_prompt_caching: bool,
        provider: str = "anthropic",
        model: str = "claude-opus-4-8",
    ) -> None:
        self._system_prompt = system_prompt
        self._enable_prompt_caching = enable_prompt_caching
        self.adapter = _StubAdapter(provider)
        # Only read by the Bedrock model gate; harmless for other providers.
        self.kwargs = {"model": model}


def test_build_messages_plain_string_when_caching_off() -> None:
    llm = _StubLLM("SYSTEM", enable_prompt_caching=False)
    messages = llm._build_messages("USER")
    assert messages == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "USER"},
    ]


def test_build_messages_tags_only_system_when_caching_on() -> None:
    llm = _StubLLM("SYSTEM", enable_prompt_caching=True)
    messages = llm._build_messages("USER")

    system, user = messages
    assert system["role"] == "system"
    assert system["content"] == [
        {
            "type": "text",
            "text": "SYSTEM",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    # The per-request user prompt is never tagged for caching.
    assert user == {"role": "user", "content": "USER"}


@pytest.mark.parametrize("provider", ["openai", "azure", "gemini", "mistral"])
def test_build_messages_not_tagged_for_unsupported_provider(provider: str) -> None:
    """Caching flag on, but a provider we don't emit cache_control for -> plain."""
    llm = _StubLLM("SYSTEM", enable_prompt_caching=True, provider=provider)
    assert llm._build_messages("USER") == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "USER"},
    ]


def test_build_messages_cache_prefix_splits_user_turn() -> None:
    llm = _StubLLM("SYSTEM", enable_prompt_caching=True)
    messages = llm._build_messages("VOLATILE", cache_prefix="STABLE")

    system, user = messages
    # System stays a plain string; the stable prefix is cached in the user turn.
    assert system == {"role": "system", "content": "SYSTEM"}
    assert user["role"] == "user"
    assert user["content"] == [
        {"type": "text", "text": "STABLE", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "VOLATILE"},
    ]
    # Text-equivalence invariant: the model sees prefix + prompt, unchanged.
    seen = "".join(block["text"] for block in user["content"])
    assert seen == "STABLE" + "VOLATILE"


def test_build_messages_cache_prefix_preserved_when_caching_off() -> None:
    """Caching off must NOT drop the prefix — the model still sees prefix+prompt.

    Regression guard: a consumer that splits its prompt into (cache_prefix,
    prompt) must produce the full text even on an unsupported provider / with
    caching disabled, otherwise the prefix (e.g. instructions/context) is lost.
    """
    llm = _StubLLM("SYSTEM", enable_prompt_caching=False)
    assert llm._build_messages("VOLATILE", cache_prefix="STABLE") == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "STABLE" + "VOLATILE"},
    ]


def test_build_messages_cache_prefix_preserved_for_unsupported_provider() -> None:
    """Flag on, but a provider we don't emit cache_control for -> full prompt, no tag."""
    llm = _StubLLM("SYSTEM", enable_prompt_caching=True, provider="openai")
    assert llm._build_messages("VOLATILE", cache_prefix="STABLE") == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "STABLE" + "VOLATILE"},
    ]


# ── Bedrock model gate: cache_control only for Anthropic/Claude on Bedrock ───

# Bedrock hosts many families; only Anthropic/Claude honor cache_control.
_BEDROCK_ANTHROPIC_MODELS = [
    "bedrock/anthropic.claude-opus-4-8-20260101-v1:0",
    "bedrock/us.anthropic.claude-sonnet-4-6-20250101-v1:0",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
]
_BEDROCK_NON_ANTHROPIC_MODELS = [
    "bedrock/amazon.titan-text-premier-v1:0",
    "bedrock/meta.llama3-70b-instruct-v1:0",
    "bedrock/cohere.command-r-plus-v1:0",
    "bedrock/mistral.mistral-large-2407-v1:0",
]


@pytest.mark.parametrize("model", _BEDROCK_ANTHROPIC_MODELS)
def test_bedrock_anthropic_model_caches(model: str) -> None:
    llm = _StubLLM("SYSTEM", enable_prompt_caching=True, provider="bedrock", model=model)
    assert llm._prompt_caching_active() is True
    # cache_control block is emitted on the split user turn.
    user = llm._build_messages("VOLATILE", cache_prefix="STABLE")[1]
    assert user["content"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.parametrize("model", _BEDROCK_NON_ANTHROPIC_MODELS)
def test_bedrock_non_anthropic_model_does_not_cache(model: str) -> None:
    """Titan/Llama/Cohere/Mistral on Bedrock must not get cache_control blocks."""
    llm = _StubLLM("SYSTEM", enable_prompt_caching=True, provider="bedrock", model=model)
    assert llm._prompt_caching_active() is False
    # Falls back to the plain string form; prefix still preserved as full text.
    assert llm._build_messages("VOLATILE", cache_prefix="STABLE") == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "STABLE" + "VOLATILE"},
    ]


def test_is_prompt_caching_active_matches_private() -> None:
    """The public probe mirrors the internal gate for callers (e.g. answer_prompt)."""
    on = _StubLLM("SYSTEM", enable_prompt_caching=True, provider="anthropic")
    assert on.is_prompt_caching_active() is True
    off_provider = _StubLLM("SYSTEM", enable_prompt_caching=True, provider="openai")
    assert off_provider.is_prompt_caching_active() is False
    off_bedrock = _StubLLM(
        "SYSTEM",
        enable_prompt_caching=True,
        provider="bedrock",
        model="bedrock/amazon.titan-text-premier-v1:0",
    )
    assert off_bedrock.is_prompt_caching_active() is False


def test_validate_bedrock_non_anthropic_never_enables_caching() -> None:
    """base1 keeps the validated flag honest: non-Anthropic Bedrock -> False."""
    result = AWSBedrockLLMParameters.validate(
        {
            "model": "amazon.titan-text-premier-v1:0",
            "enable_prompt_caching": True,
            "aws_region_name": "us-east-1",
        }
    )
    assert result["enable_prompt_caching"] is False


# ── cost accounting: cached calls price against the cost_model override ──────


def test_cost_override_passed_to_completion_cost_on_cached_call(monkeypatch) -> None:
    """On a cached call, completion_cost must receive model= so the cost_model
    override is honored (matching the cost_per_token fallback path).
    """
    import unstract.sdk1.llm as llm_mod
    from unstract.sdk1.llm import LLM

    captured: dict[str, Any] = {}

    def _fake_completion_cost(**kwargs: Any) -> float:
        captured.update(kwargs)
        return 0.42

    monkeypatch.setattr(llm_mod.litellm, "completion_cost", _fake_completion_cost)

    cost = LLM._compute_call_cost(
        object(),
        model="anthropic/claude-opus-4-8",
        prompt_tokens=100,
        completion_tokens=10,
        has_cache_tokens=True,
        response={"id": "resp"},
    )
    assert cost == 0.42
    assert captured.get("model") == "anthropic/claude-opus-4-8"
    assert captured.get("completion_response") == {"id": "resp"}


# ── constructor / env opt-in (real LLM, no flag in adapter metadata) ────────

_ANTHROPIC_ADAPTER_ID = "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203"


def test_constructor_flag_forces_caching_without_metadata(monkeypatch) -> None:
    """A caller that builds by adapter without the stored flag can still opt in."""
    monkeypatch.delenv("ENABLE_PROMPT_CACHING", raising=False)
    from unstract.sdk1.llm import LLM

    meta = {"model": "claude-opus-4-8", "api_key": "sk-test"}
    llm = LLM(
        adapter_id=_ANTHROPIC_ADAPTER_ID,
        adapter_metadata=meta,
        system_prompt="S",
        enable_prompt_caching=True,
    )
    assert llm._enable_prompt_caching is True
    # cache_prefix path produces the split user turn end to end.
    messages = llm._build_messages("VOLATILE", cache_prefix="STABLE")
    assert messages[1]["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_constructor_flag_defaults_off(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_PROMPT_CACHING", raising=False)
    from unstract.sdk1.llm import LLM

    meta = {"model": "claude-opus-4-8", "api_key": "sk-test"}
    llm = LLM(adapter_id=_ANTHROPIC_ADAPTER_ID, adapter_metadata=meta, system_prompt="S")
    assert llm._enable_prompt_caching is False


def test_env_var_enables_caching_platform_wide(monkeypatch) -> None:
    """The ENABLE_PROMPT_CACHING master switch turns caching on with no per-call flag."""
    monkeypatch.setenv("ENABLE_PROMPT_CACHING", "true")
    from unstract.sdk1.llm import LLM, is_prompt_caching_enabled

    assert is_prompt_caching_enabled() is True
    meta = {"model": "claude-opus-4-8", "api_key": "sk-test"}
    llm = LLM(adapter_id=_ANTHROPIC_ADAPTER_ID, adapter_metadata=meta, system_prompt="S")
    assert llm._enable_prompt_caching is True
