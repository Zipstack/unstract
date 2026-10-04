"""Tests for the sampling-parameter strip.

Covers Claude Opus 4.7 and every model released since (Opus 4.8, Sonnet 5,
Fable 5, Mythos 5), all of which reject `temperature`/`top_p`/`top_k`. Sonnet 5
is the model behind the reported Azure AI Foundry `temperature is deprecated`
failure. Also covers OpenAI's GPT-6 family, which rejects `temperature` on AWS
Bedrock while GPT-5.6 still accepts it.

Pins the detection regex and the four-adapter wiring against the failure
modes that surfaced in PR #1934 review:
- prefix collisions (`claude-opus-4-70`, `-75`, `4-7verbose`)
- Bedrock Application Inference Profile ARN fallback via `model_id`
- mutate-and-return regression (input dict must be preserved)
- silent skip with sampling params present must emit a debug breadcrumb
- every adapter calls the strip on its return path
"""

import logging
from typing import Any

import pytest
from unstract.sdk1.adapters.base1 import (
    _DEPRECATED_SAMPLING_PARAMS,
    AnthropicLLMParameters,
    AWSBedrockLLMParameters,
    AzureAIFoundryLLMParameters,
    AzureOpenAILLMParameters,
    OpenAILLMParameters,
    VertexAILLMParameters,
    _has_deprecated_sampling_params,
    _strip_deprecated_sampling_params,
)
from unstract.sdk1.llm import LLM

# ── detection: positives ────────────────────────────────────────────────────

OPUS_47_POSITIVES: list[str] = [
    # Native Anthropic
    "claude-opus-4-7",
    "anthropic/claude-opus-4-7",
    "Claude-Opus-4-7",  # case
    # Bedrock foundation model id with date stamp
    "anthropic.claude-opus-4-7-20260101-v1:0",
    "bedrock/anthropic.claude-opus-4-7-20260101-v1:0",
    # Bedrock route prefixes pass through the trailing-edge anchor
    "bedrock/converse/anthropic.claude-opus-4-7-20260101-v1:0",
    "bedrock/invoke/anthropic.claude-opus-4-7-20260101-v1:0",
    # Bedrock cross-region inference profiles
    "us.anthropic.claude-opus-4-7-20260101-v1:0",
    "bedrock/us.anthropic.claude-opus-4-7-20260101-v1:0",
    "bedrock/eu.anthropic.claude-opus-4-7-20260101-v1:0",
    "bedrock/apac.anthropic.claude-opus-4-7-20260101-v1:0",
    "bedrock/global.anthropic.claude-opus-4-7-20260101-v1:0",
    # Bedrock foundation-model ARN
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-opus-4-7-20260101-v1:0",
    # Bedrock inference-profile ARN (cross-region)
    "arn:aws:bedrock:us-east-1:000000000000:inference-profile/us.anthropic.claude-opus-4-7-20260101-v1:0",
    # Vertex AI
    "vertex_ai/claude-opus-4-7@20260101",
    "vertex_ai/claude-opus-4-7",
    # Azure AI Foundry deployments embedding the model id
    "azure_ai/claude-opus-4-7",
    "azure_ai/claude-opus-4-7-prod",
    "azure_ai/my-claude-opus-4-7-deployment",
    # Separator variants — Anthropic uses dashes, but the normalize step
    # collapses `.` and `_` so dot/underscore forms still match
    "claude.opus.4.7",
    "claude_opus_4_7",
    # Version tag accepted only as `v\d` after the trailing edge
    "claude-opus-4-7v1",
    "claude-opus-4-7v9",
]


@pytest.mark.parametrize("model", OPUS_47_POSITIVES)
def test_has_deprecated_sampling_params_positive(model: str) -> None:
    assert _has_deprecated_sampling_params(model)


# Every Claude model released after Opus 4.7 also rejects sampling params
# (Opus 4.8, Sonnet 5, Fable 5, Mythos 5). Sonnet 5 is the model behind the
# reported Azure AI Foundry `temperature is deprecated` failure.
POST_47_POSITIVES: list[str] = [
    # Sonnet 5 — native, Azure AI Foundry (prefixed by validate_model), case,
    # deployment names embedding the id, separator normalization, version tag
    "claude-sonnet-5",
    "anthropic/claude-sonnet-5",
    "azure_ai/claude-sonnet-5",
    "azure_ai/claude-sonnet-5-prod",
    "azure_ai/my-claude-sonnet-5-deployment",
    "Claude-Sonnet-5",  # case
    "claude.sonnet.5",  # dot separators
    "claude_sonnet_5",  # underscore separators
    "claude-sonnet-5v1",  # version tag
    "anthropic.claude-sonnet-5-20260101-v1:0",  # Bedrock foundation model id
    "vertex_ai/claude-sonnet-5@20260101",  # Vertex AI
    # Opus 4.8
    "claude-opus-4-8",
    "anthropic.claude-opus-4-8-20260101-v1:0",
    "azure_ai/claude-opus-4-8",
    # Fable 5 / Mythos 5
    "claude-fable-5",
    "vertex_ai/claude-fable-5@20260101",
    "claude-mythos-5",
]


@pytest.mark.parametrize("model", POST_47_POSITIVES)
def test_has_deprecated_sampling_params_positive_post_opus_47(model: str) -> None:
    assert _has_deprecated_sampling_params(model)


# OpenAI's GPT-6 family rejects `temperature`, so the strip must fire for every
# encoding Bedrock (Mantle and Converse) and Azure AI Foundry hand us.
GPT6_POSITIVES: list[str] = [
    "openai.gpt-6-luna",
    "bedrock_mantle/openai.gpt-6-luna",
    "bedrock/openai.gpt-6-sol",
    "us.openai.gpt-6-astra",
    "bedrock/global.openai.gpt-6.1-sol",  # `.1` point release normalizes to `-1`
    "azure_ai/gpt-6-sol",
    "gpt-6-luna",
]


@pytest.mark.parametrize("model", GPT6_POSITIVES)
def test_has_deprecated_sampling_params_positive_gpt_6(model: str) -> None:
    assert _has_deprecated_sampling_params(model)


# ── detection: negatives ────────────────────────────────────────────────────

NEGATIVES: list[str | None] = [
    # Adjacent Claude model families that retain temperature
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-sonnet-4-7",
    "claude-haiku-4-5",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    # Sonnet families that still accept sampling params must NOT match the
    # `claude-sonnet-5` stem
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    # Prefix collisions / alpha continuations for the new stems — lock the
    # trailing-edge anchor the same way it is locked for opus-4-7
    "claude-sonnet-50",
    "claude-sonnet-59",
    "claude-sonnet-5verbose",
    "claude-sonnet-5variant",
    "claude-opus-4-80",
    "claude-fable-50",
    # Non-Anthropic providers
    "gpt-4o",
    # GPT-5.x still accepts temperature; `gpt-5.6-*` normalizes to `gpt-5-6-*`
    # and must NOT match the `gpt-6` stem
    "openai.gpt-5.6-luna",
    "bedrock_mantle/openai.gpt-5.6-terra",
    "bedrock_mantle/openai.gpt-5.5",
    "openai.gpt-oss-120b",
    # Prefix collision for the `gpt-6` stem
    "gpt-60",
    "gemini-2.0-flash",
    "mistral-large-latest",
    # Prefix collisions — lock the trailing-edge anchor against future
    # versions whose id starts with `claude-opus-4-7` but is unrelated.
    "claude-opus-4-70",
    "claude-opus-4-75",
    "claude-opus-4-79",
    "anthropic/claude-opus-4-70",
    "bedrock/anthropic.claude-opus-4-71-20260101-v1:0",
    # Bare-`v` alpha continuations must NOT match (HIGH line 41 fix).
    "claude-opus-4-7verbose",
    "claude-opus-4-7vnext",
    "claude-opus-4-7variant",
    # Opaque Bedrock Application Inference Profile ARN — model id is not
    # recoverable from the string. Strip-detection is expected to skip;
    # callers must keep the standard id in `model` or `model_id`.
    "arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/abcd1234efgh",
    # Empty / missing
    None,
    "",
]


@pytest.mark.parametrize("model", NEGATIVES)
def test_has_deprecated_sampling_params_negative(model: str | None) -> None:
    assert not _has_deprecated_sampling_params(model)


# ── strip contract ──────────────────────────────────────────────────────────


def test_strip_returns_copy_without_mutating_input() -> None:
    inp: dict[str, Any] = {"model": "claude-opus-4-7", "temperature": 0.5}
    out = _strip_deprecated_sampling_params(inp)
    assert out is not inp
    assert inp == {"model": "claude-opus-4-7", "temperature": 0.5}
    assert "temperature" not in out


def test_strip_removes_all_three_sampling_params() -> None:
    inp = {
        "model": "claude-opus-4-7",
        "temperature": 0.5,
        "top_p": 0.9,
        "top_k": 40,
    }
    out = _strip_deprecated_sampling_params(inp)
    for param in _DEPRECATED_SAMPLING_PARAMS:
        assert param not in out, f"{param} should be stripped"


def test_strip_via_model_id_field_when_model_is_opaque_aip_arn() -> None:
    """Bedrock AIP fallback: opaque ARN in `model`, real id in `model_id`."""
    inp = {
        "model": "bedrock/arn:aws:bedrock:us-east-1:0:application-inference-profile/abcd",
        "model_id": "anthropic.claude-opus-4-7-20260101-v1:0",
        "temperature": 0.5,
    }
    out = _strip_deprecated_sampling_params(inp)
    assert "temperature" not in out


def test_strip_via_model_field_when_model_id_is_opaque_aip_arn() -> None:
    """Bedrock AIP fallback: standard id in `model`, opaque ARN in `model_id`."""
    inp = {
        "model": "bedrock/anthropic.claude-opus-4-7-20260101-v1:0",
        "model_id": "arn:aws:bedrock:us-east-1:0:application-inference-profile/abcd",
        "temperature": 0.5,
    }
    out = _strip_deprecated_sampling_params(inp)
    assert "temperature" not in out


def test_strip_skipped_when_both_fields_opaque_and_logs_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Documented limitation: opaque-only state must emit a breadcrumb.

    With no model id in any field, the strip is a no-op; the debug log makes
    the upstream 400 traceable.
    """
    inp = {
        "model": "bedrock/arn:aws:bedrock:us-east-1:0:application-inference-profile/abcd",
        "model_id": "arn:aws:bedrock:us-east-1:0:application-inference-profile/efgh",
        "temperature": 0.5,
    }
    with caplog.at_level(logging.DEBUG, logger="unstract.sdk1.adapters.base1"):
        out = _strip_deprecated_sampling_params(inp)
    # Documented limitation: not stripped when no field carries the model id.
    assert out["temperature"] == pytest.approx(0.5)
    assert any(
        "Sampling-param strip skipped" in rec.message for rec in caplog.records
    ), "expected debug breadcrumb when strip is a no-op"


def test_strip_does_not_log_when_no_sampling_params_present(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The breadcrumb stays quiet on the common no-op path.

    No model id field looks opaque, so the strip-skipped state is not worth
    a debug breadcrumb.
    """
    inp = {"model": "gpt-4o"}
    with caplog.at_level(logging.DEBUG, logger="unstract.sdk1.adapters.base1"):
        _strip_deprecated_sampling_params(inp)
    assert not any(
        "Sampling-param strip skipped" in rec.message for rec in caplog.records
    )


def test_strip_does_not_log_when_sampling_params_present_but_model_not_opaque(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-deprecated models with default `temperature` must not emit noise.

    `BaseChatCompletionParameters` declares `temperature: float | None =
    Field(default=0.1)`, so every adapter's `validate()` returns a dict that
    carries `temperature`. If the breadcrumb keyed off "any sampling param
    present" it would fire for every routine call to `claude-3-5-sonnet`,
    `claude-opus-4-6`, `gpt-4o`, etc. — pure log noise. The guard must
    instead key off an opaque-looking model id field.
    """
    inp = {"model": "claude-3-5-sonnet-20241022", "temperature": 0.1}
    with caplog.at_level(logging.DEBUG, logger="unstract.sdk1.adapters.base1"):
        _strip_deprecated_sampling_params(inp)
    assert not any(
        "Sampling-param strip skipped" in rec.message for rec in caplog.records
    )


def test_strip_retains_temperature_for_non_deprecated_models() -> None:
    inp = {"model": "claude-3-5-sonnet-20241022", "temperature": 0.5}
    out = _strip_deprecated_sampling_params(inp)
    assert out["temperature"] == pytest.approx(0.5)


# ── adapter wiring (regression guard for the Vertex AI gap) ─────────────────


def _vertex_metadata(model: str, temperature: float = 0.5) -> dict[str, Any]:
    return {
        "model": model,
        "vertex_credentials": "{}",
        "vertex_project": "p",
        "safety_settings": {},
        "temperature": temperature,
    }


ADAPTER_CASES: list[tuple[str, type, dict[str, Any]]] = [
    (
        "anthropic",
        AnthropicLLMParameters,
        {"api_key": "k"},
    ),
    (
        "bedrock",
        AWSBedrockLLMParameters,
        {"aws_region_name": "us-east-1"},
    ),
    (
        "azure_ai_foundry",
        AzureAIFoundryLLMParameters,
        {"api_key": "k", "api_base": "https://x.inference.ai.azure.com"},
    ),
]


@pytest.mark.parametrize(
    "name,cls,extra",
    ADAPTER_CASES,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_validate_strips_temperature_for_opus_4_7(
    name: str, cls: type, extra: dict[str, Any]
) -> None:
    """Every adapter that proxies Anthropic must drop temperature on return.

    The Vertex AI gap (commit 5a4ea27f shipped without it, fixed in 7fb66f15)
    is exactly the regression this locks in.
    """
    model = {
        "anthropic": "claude-opus-4-7",
        "bedrock": "anthropic.claude-opus-4-7-20260101-v1:0",
        "azure_ai_foundry": "claude-opus-4-7",
    }[name]
    result = cls.validate({"model": model, "temperature": 0.5, **extra})
    for param in _DEPRECATED_SAMPLING_PARAMS:
        assert param not in result, f"{name}: {param} should be stripped"


def test_vertex_validate_strips_temperature_for_opus_4_7() -> None:
    result = VertexAILLMParameters.validate(_vertex_metadata("claude-opus-4-7@20260101"))
    for param in _DEPRECATED_SAMPLING_PARAMS:
        assert param not in result, f"vertex: {param} should be stripped"


@pytest.mark.parametrize(
    "name,cls,extra",
    ADAPTER_CASES,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_validate_strips_temperature_for_sonnet_5(
    name: str, cls: type, extra: dict[str, Any]
) -> None:
    """Sonnet 5 rejects temperature just like Opus 4.7.

    The `azure_ai_foundry` case is the exact scenario reported: configuring
    Claude Sonnet 5 on Azure AI Foundry 400'd with `temperature is deprecated`.
    """
    model = {
        "anthropic": "claude-sonnet-5",
        "bedrock": "anthropic.claude-sonnet-5-20260101-v1:0",
        "azure_ai_foundry": "claude-sonnet-5",
    }[name]
    result = cls.validate({"model": model, "temperature": 0.5, **extra})
    for param in _DEPRECATED_SAMPLING_PARAMS:
        assert param not in result, f"{name}: {param} should be stripped"


def test_vertex_validate_strips_temperature_for_sonnet_5() -> None:
    result = VertexAILLMParameters.validate(_vertex_metadata("claude-sonnet-5@20260101"))
    for param in _DEPRECATED_SAMPLING_PARAMS:
        assert param not in result, f"vertex: {param} should be stripped"


@pytest.mark.parametrize(
    "name,cls,extra",
    ADAPTER_CASES,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_validate_retains_temperature_for_opus_4_6(
    name: str, cls: type, extra: dict[str, Any]
) -> None:
    """Non-deprecated Claude models must keep temperature intact."""
    model = {
        "anthropic": "claude-opus-4-6",
        "bedrock": "anthropic.claude-opus-4-6-20251022-v1:0",
        "azure_ai_foundry": "claude-opus-4-6",
    }[name]
    result = cls.validate({"model": model, "temperature": 0.5, **extra})
    assert result["temperature"] == pytest.approx(0.5)


def test_vertex_validate_retains_temperature_for_gemini() -> None:
    result = VertexAILLMParameters.validate(_vertex_metadata("gemini-2.0-flash"))
    assert result["temperature"] == pytest.approx(0.5)


# ── Bedrock GPT-6 (Mantle and Converse routes) ──────────────────────────────

_BEDROCK_EXTRA: dict[str, Any] = {"aws_region_name": "us-east-1"}


@pytest.mark.parametrize(
    "model",
    ["openai.gpt-6-luna", "bedrock_mantle/openai.gpt-6-luna", "bedrock/openai.gpt-6-sol"],
)
def test_bedrock_validate_strips_temperature_for_gpt_6(model: str) -> None:
    """GPT-6 on Bedrock 400s with `temperature not permitted` on any value.

    Covers the unprefixed id as well as both explicit routes: whether an
    unprefixed GPT-6 id lands on Mantle or Converse depends on the LiteLLM
    registry loaded, and the strip has to hold on either.
    """
    result = AWSBedrockLLMParameters.validate(
        {"model": model, "temperature": 0.5, **_BEDROCK_EXTRA}
    )
    for param in _DEPRECATED_SAMPLING_PARAMS:
        assert param not in result, f"{model}: {param} should be stripped"


def test_bedrock_validate_strips_reasoning_temperature_for_gpt_6() -> None:
    """The reasoning config's `temperature = 1` write is stripped too.

    `_apply_bedrock_reasoning_config` forces `temperature = 1` when Extended
    Thinking is on; that must not reach GPT-6, while `reasoning_effort` must.
    """
    result = AWSBedrockLLMParameters.validate(
        {
            "model": "bedrock_mantle/openai.gpt-6-luna",
            "enable_thinking": True,
            **_BEDROCK_EXTRA,
        }
    )
    assert "temperature" not in result
    assert result["reasoning_effort"] == "medium"


def test_bedrock_validate_gpt_6_strip_survives_revalidation() -> None:
    """`LLM.complete()` re-validates the stored kwargs on every call.

    The absent `temperature` key must not be refilled by Pydantic's 0.1
    default on the second pass.
    """
    first = AWSBedrockLLMParameters.validate(
        {
            "model": "bedrock_mantle/openai.gpt-6-luna",
            "enable_thinking": True,
            **_BEDROCK_EXTRA,
        }
    )
    second = AWSBedrockLLMParameters.validate(dict(first))
    assert "temperature" not in second
    assert second["reasoning_effort"] == "medium"
    assert second["model"] == "bedrock_mantle/openai.gpt-6-luna"


def test_bedrock_validate_retains_temperature_for_gpt_5_6() -> None:
    """GPT-5.6 accepts temperature, so the GPT-6 stem must leave it alone."""
    result = AWSBedrockLLMParameters.validate(
        {"model": "openai.gpt-5.6-terra", "temperature": 0.5, **_BEDROCK_EXTRA}
    )
    assert result["temperature"] == pytest.approx(0.5)


# ── GPT-6 on native OpenAI, Azure OpenAI and Azure AI Foundry ───────────────

_OPENAI_EXTRA: dict[str, Any] = {"api_key": "k", "api_base": "https://api.openai.com/v1"}


@pytest.mark.parametrize("enable_reasoning", [False, True])
def test_openai_validate_strips_temperature_for_gpt_6(enable_reasoning: bool) -> None:
    """Reasoning forces `temperature = 1`; GPT-6 must get no temperature at all."""
    first = OpenAILLMParameters.validate(
        {"model": "gpt-6-luna", "enable_reasoning": enable_reasoning, **_OPENAI_EXTRA}
    )
    assert "temperature" not in first
    # `LLM.complete()` re-validates the stored kwargs; the model id still names
    # GPT-6, so the strip fires again rather than the 0.1 default leaking back.
    second = OpenAILLMParameters.validate(dict(first))
    assert "temperature" not in second
    if enable_reasoning:
        assert second["reasoning_effort"] == "medium"


def test_openai_validate_retains_temperature_for_gpt_5() -> None:
    result = OpenAILLMParameters.validate(
        {"model": "gpt-5", "enable_reasoning": True, **_OPENAI_EXTRA}
    )
    assert result["temperature"] == 1


def _azure_metadata(**overrides: str | bool) -> dict[str, Any]:
    return {
        "api_key": "k",
        "azure_endpoint": "https://x.openai.azure.com/",
        "api_version": "2024-10-21",
        **overrides,
    }


def _azure_revalidate(
    first: dict[str, Any], **call_kwargs: float | str
) -> dict[str, Any]:
    """Re-validate through `LLM._revalidate`, the path every completion takes.

    `LLM` sets `cost_model` aside at construction and merges per-call kwargs
    over the stored ones, so this drives the real method on a bare instance
    rather than re-implementing that merge here.
    """
    llm = LLM.__new__(LLM)
    llm.adapter = AzureOpenAILLMParameters
    llm.kwargs = dict(first)
    llm._cost_model = llm.kwargs.pop("cost_model", None)
    return llm._revalidate(call_kwargs)


@pytest.mark.parametrize("enable_reasoning", [False, True])
def test_azure_validate_drops_temperature_for_gpt_6_behind_opaque_deployment(
    enable_reasoning: bool,
) -> None:
    """The deployment name hides the model; the `model` field names GPT-6.

    On re-validation only the deployment name is left in `model`, so the
    strip has to hold off `cost_model`, which `LLM` passes back -- otherwise
    Azure's `temperature` default of 1 (or reasoning's forced 1) returns.
    """
    first = AzureOpenAILLMParameters.validate(
        _azure_metadata(
            model="gpt-6-luna",
            deployment_name="prod-chat",
            enable_reasoning=enable_reasoning,
        )
    )
    assert first["model"] == "azure/prod-chat"
    assert first["cost_model"] == "azure/gpt-6-luna"
    assert "temperature" not in first

    second = _azure_revalidate(first)
    assert "temperature" not in second
    assert second["cost_model"] == "azure/gpt-6-luna"
    if enable_reasoning:
        assert second["reasoning_effort"] == "medium"


def test_azure_revalidate_drops_per_call_temperature_for_gpt_6() -> None:
    """A caller-supplied `temperature` must not reach an opaque GPT-6 deployment.

    Cloud callers pass `temperature=` to `complete()` / `complete_vision()`;
    detection keys off `cost_model`, which a per-call kwarg cannot displace.
    """
    first = AzureOpenAILLMParameters.validate(
        _azure_metadata(model="gpt-6-luna", deployment_name="prod-chat")
    )
    second = _azure_revalidate(first, temperature=0.5)
    assert "temperature" not in second


def test_azure_validate_drops_temperature_when_deployment_names_gpt_6() -> None:
    first = AzureOpenAILLMParameters.validate(
        _azure_metadata(deployment_name="gpt-6-sol")
    )
    assert "temperature" not in first
    assert "temperature" not in _azure_revalidate(first, temperature=0.5)


@pytest.mark.parametrize("enable_reasoning", [False, True])
def test_azure_validate_retains_temperature_for_other_models(
    enable_reasoning: bool,
) -> None:
    first = AzureOpenAILLMParameters.validate(
        _azure_metadata(
            model="gpt-5",
            deployment_name="prod-chat",
            enable_reasoning=enable_reasoning,
        )
    )
    assert first["temperature"] == 1
    assert _azure_revalidate(first)["temperature"] == 1


def test_azure_revalidate_keeps_per_call_temperature_for_other_models() -> None:
    first = AzureOpenAILLMParameters.validate(
        _azure_metadata(model="gpt-4o", deployment_name="prod-chat")
    )
    assert _azure_revalidate(first, temperature=0.5)["temperature"] == 0.5


def test_azure_ai_foundry_validate_strips_temperature_for_gpt_6() -> None:
    result = AzureAIFoundryLLMParameters.validate(
        {
            "model": "gpt-6-sol",
            "api_key": "k",
            "api_base": "https://x.services.ai.azure.com/models",
            "temperature": 0.5,
        }
    )
    assert "temperature" not in result
