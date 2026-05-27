"""Tests for Claude Opus 4.7 sampling-parameter strip.

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
    VertexAILLMParameters,
    _has_deprecated_sampling_params,
    _strip_deprecated_sampling_params,
)

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


# ── detection: negatives ────────────────────────────────────────────────────

NEGATIVES: list[str | None] = [
    # Adjacent Claude model families that retain temperature
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-sonnet-4-7",
    "claude-haiku-4-5",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    # Non-Anthropic providers
    "gpt-4o",
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
