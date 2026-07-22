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
    _PROMPT_CACHE_PROVIDERS = LLM._PROMPT_CACHE_PROVIDERS

    def __init__(
        self,
        system_prompt: str,
        enable_prompt_caching: bool,
        provider: str = "anthropic",
    ) -> None:
        self._system_prompt = system_prompt
        self._enable_prompt_caching = enable_prompt_caching
        self.adapter = _StubAdapter(provider)


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


def test_build_messages_cache_prefix_ignored_when_caching_off() -> None:
    llm = _StubLLM("SYSTEM", enable_prompt_caching=False)
    assert llm._build_messages("VOLATILE", cache_prefix="STABLE") == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "VOLATILE"},
    ]


# ── constructor opt-in (real LLM, no flag in adapter metadata) ──────────────

_ANTHROPIC_ADAPTER_ID = "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203"


def test_constructor_flag_forces_caching_without_metadata() -> None:
    """A caller that builds by adapter without the stored flag can still opt in."""
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


def test_constructor_flag_defaults_off() -> None:
    from unstract.sdk1.llm import LLM

    meta = {"model": "claude-opus-4-8", "api_key": "sk-test"}
    llm = LLM(adapter_id=_ANTHROPIC_ADAPTER_ID, adapter_metadata=meta, system_prompt="S")
    assert llm._enable_prompt_caching is False
