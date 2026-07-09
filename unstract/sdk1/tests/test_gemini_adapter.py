"""Unit tests for the Gemini LLM adapter (UNS-480 / UNS-482)."""

import json
from pathlib import Path

import pytest
from unstract.sdk1.adapters.base1 import GeminiLLMParameters
from unstract.sdk1.adapters.llm1.gemini import GeminiLLMAdapter

BASE_METADATA = {"api_key": "test-key", "model": "gemini-2.5-flash"}


# ── validate_model ───────────────────────────────────────────────────────────


def test_validate_model_prefixes_when_missing() -> None:
    assert (
        GeminiLLMParameters.validate_model({"model": "gemini-2.5-flash"})
        == "gemini/gemini-2.5-flash"
    )


def test_validate_model_does_not_double_prefix() -> None:
    assert (
        GeminiLLMParameters.validate_model({"model": "gemini/gemini-2.5-pro"})
        == "gemini/gemini-2.5-pro"
    )


def test_validate_model_blank_raises() -> None:
    with pytest.raises(ValueError, match="model is required"):
        GeminiLLMParameters.validate_model({"model": "   "})


# ── validate: thinking disabled ──────────────────────────────────────────────


def test_validate_thinking_disabled_by_default() -> None:
    result = GeminiLLMParameters.validate({**BASE_METADATA, "temperature": 0.3})
    assert result["model"] == "gemini/gemini-2.5-flash"
    assert "thinking" not in result
    assert result["temperature"] == pytest.approx(0.3)


def test_validate_excludes_control_fields_from_model() -> None:
    result = GeminiLLMParameters.validate(BASE_METADATA.copy())
    assert "enable_thinking" not in result
    assert "budget_tokens" not in result


# ── validate: thinking enabled ───────────────────────────────────────────────


def test_validate_thinking_enabled_with_budget() -> None:
    result = GeminiLLMParameters.validate(
        {**BASE_METADATA, "enable_thinking": True, "budget_tokens": 2048}
    )
    assert result["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert result["temperature"] == 1


def test_validate_thinking_overrides_user_temperature() -> None:
    result = GeminiLLMParameters.validate(
        {
            **BASE_METADATA,
            "temperature": 0.7,
            "enable_thinking": True,
            "budget_tokens": 1024,
        }
    )
    assert result["temperature"] == 1


def test_validate_thinking_enabled_without_budget_raises() -> None:
    with pytest.raises(ValueError, match="budget_tokens is required"):
        GeminiLLMParameters.validate({**BASE_METADATA, "enable_thinking": True})


def test_validate_thinking_budget_tokens_invalid_type_raises() -> None:
    with pytest.raises(ValueError, match="budget_tokens must be an integer >= 1024"):
        GeminiLLMParameters.validate(
            {**BASE_METADATA, "enable_thinking": True, "budget_tokens": "hello"}
        )


def test_validate_thinking_budget_tokens_too_small_raises() -> None:
    with pytest.raises(ValueError, match="budget_tokens must be an integer >= 1024"):
        GeminiLLMParameters.validate(
            {**BASE_METADATA, "enable_thinking": True, "budget_tokens": 512}
        )


def test_validate_preserves_existing_thinking_config() -> None:
    existing = {"type": "enabled", "budget_tokens": 4096}
    result = GeminiLLMParameters.validate({**BASE_METADATA, "thinking": existing})
    assert result["thinking"] == existing
    assert result["temperature"] == 1


def test_validate_does_not_mutate_input() -> None:
    metadata = {**BASE_METADATA, "enable_thinking": True, "budget_tokens": 2048}
    snapshot = metadata.copy()
    GeminiLLMParameters.validate(metadata)
    assert metadata == snapshot


# ── Pydantic field surface ───────────────────────────────────────────────────


def test_thinking_controls_not_pydantic_fields() -> None:
    fields = GeminiLLMParameters.model_fields
    assert "enable_thinking" not in fields
    assert "budget_tokens" not in fields
    assert "thinking" not in fields
    assert "api_key" in fields


def test_api_key_is_required() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GeminiLLMParameters(model="gemini/gemini-2.5-flash")


# ── Adapter identity ─────────────────────────────────────────────────────────


def test_adapter_identity() -> None:
    assert GeminiLLMAdapter.get_name() == "Gemini"
    assert GeminiLLMAdapter.get_provider() == "gemini"
    assert GeminiLLMAdapter.get_id().startswith("gemini|")
    metadata = GeminiLLMAdapter.get_metadata()
    assert metadata["is_active"] is True
    assert metadata["name"] == "Gemini"


# ── JSON schema ──────────────────────────────────────────────────────────────


@pytest.fixture
def gemini_schema() -> dict:
    schema_path = (
        Path(__file__).parent.parent
        / "src/unstract/sdk1/adapters/llm1/static/gemini.json"
    )
    return json.loads(schema_path.read_text())


def test_schema_required_fields(gemini_schema: dict) -> None:
    assert set(gemini_schema["required"]) >= {"adapter_name", "api_key", "model"}


def test_schema_enable_thinking_default_false(gemini_schema: dict) -> None:
    assert gemini_schema["properties"]["enable_thinking"]["default"] is False


def test_schema_budget_tokens_conditional(gemini_schema: dict) -> None:
    all_of = gemini_schema["allOf"]
    assert len(all_of) == 1
    conditional = all_of[0]
    assert conditional["if"]["properties"]["enable_thinking"]["const"] is True
    then_block = conditional["then"]
    assert "budget_tokens" in then_block["required"]
    budget = then_block["properties"]["budget_tokens"]
    assert budget["minimum"] == 1024
    assert budget["default"] == 1024
    assert "maximum" not in budget
