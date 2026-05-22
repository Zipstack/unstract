import json
from functools import lru_cache
from importlib import import_module
from unittest.mock import MagicMock, patch

from unstract.sdk1.adapters.base1 import OpenAICompatibleLLMParameters
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.llm1 import adapters
from unstract.sdk1.adapters.llm1.openai_compatible import OpenAICompatibleLLMAdapter

OPENAI_COMPATIBLE_DESCRIPTION = (
    "Adapter for servers that implement the OpenAI Chat Completions API "
    "(vLLM, LM Studio, self-hosted gateways, and third-party providers). "
    "Use OpenAI for the official OpenAI service."
)


@lru_cache(maxsize=1)
def _load_llm_module() -> object:
    import sys
    from types import ModuleType

    # Stub python-magic so importing LLM does not depend on libmagic
    # being available in the test environment. sys.modules entries set
    # here must persist (no patch.dict) so litellm and other lazy-loaded
    # modules stay resolvable across tests.
    sys.modules.setdefault("magic", ModuleType("magic"))
    return import_module("unstract.sdk1.llm")


def _load_llm_class() -> type:
    return _load_llm_module().LLM


def test_openai_compatible_adapter_is_registered() -> None:
    adapter_id = OpenAICompatibleLLMAdapter.get_id()

    assert adapter_id in adapters
    assert adapters[adapter_id][Common.MODULE] is OpenAICompatibleLLMAdapter


def test_openai_compatible_validate_prefixes_model() -> None:
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://gateway.example.com/v1",
            "api_key": "test-key",
            "model": "gateway-model",
        }
    )

    assert validated["model"] == "custom_openai/gateway-model"


def test_openai_compatible_validate_preserves_prefixed_model() -> None:
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://gateway.example.com/v1",
            "model": "custom_openai/openai/gpt-4o",
        }
    )

    assert validated["model"] == "custom_openai/openai/gpt-4o"
    assert validated["api_key"] is None


def test_openai_compatible_validate_normalizes_blank_api_key_to_none() -> None:
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://gateway.example.com/v1",
            "api_key": "   ",
            "model": "gateway-model",
        }
    )

    assert validated["api_key"] is None


def test_openai_compatible_schema_is_loadable() -> None:
    schema = json.loads(OpenAICompatibleLLMAdapter.get_json_schema())

    assert schema["title"] == "OpenAI Compatible"
    assert schema["properties"]["api_key"]["type"] == ["string", "null"]
    assert "default" not in schema["properties"]["model"]
    assert "gateway-model" in schema["properties"]["model"]["description"]
    assert "ERNIE" not in schema["properties"]["model"]["description"]
    assert "qianfan" not in schema["properties"]["api_base"]["description"].lower()
    assert "default" not in schema["properties"]["api_base"]


def test_openai_compatible_schema_exposes_reasoning_toggle() -> None:
    schema = json.loads(OpenAICompatibleLLMAdapter.get_json_schema())

    reasoning_flag = schema["properties"]["enable_reasoning"]
    assert reasoning_flag["type"] == "boolean"
    assert reasoning_flag["default"] is False

    reasoning_branch = next(
        branch
        for branch in schema["allOf"]
        if branch["if"]["properties"]["enable_reasoning"]["const"] is True
    )
    effort = reasoning_branch["then"]["properties"]["reasoning_effort"]
    assert effort["enum"] == ["low", "medium", "high"]
    assert effort["default"] == "medium"
    assert reasoning_branch["then"]["required"] == ["reasoning_effort"]


def test_openai_compatible_validate_routes_reasoning_via_extra_body() -> None:
    # GPT-5 / o-series via custom_openai: LiteLLM does NOT auto-translate
    # `max_tokens` to `max_completion_tokens` or drop `temperature`, so the
    # adapter must do both — and route reasoning_effort / max_completion_tokens
    # through `extra_body` (the only field LiteLLM's custom_openai forwards
    # to the upstream API without rewriting).
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "model": "gpt-5",
            "max_tokens": 4096,
            "enable_reasoning": True,
            "reasoning_effort": "high",
        }
    )

    assert validated["model"] == "custom_openai/gpt-5"
    assert "temperature" not in validated
    assert "max_tokens" not in validated
    assert "reasoning_effort" not in validated
    assert "enable_reasoning" not in validated
    assert validated["extra_body"] == {
        "reasoning_effort": "high",
        "max_completion_tokens": 4096,
    }


def test_reasoning_omits_max_completion_tokens_when_unset() -> None:
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-5",
            "enable_reasoning": True,
        }
    )

    assert validated["extra_body"] == {"reasoning_effort": "medium"}
    assert "max_tokens" not in validated
    assert "temperature" not in validated


def test_openai_compatible_validate_infers_reasoning_from_effort_field() -> None:
    # When the adapter is re-validated (e.g. on second call), `enable_reasoning`
    # may already have been consumed but `reasoning_effort` should still trigger
    # the reasoning code path so the model keeps working.
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-5",
            "max_tokens": 2048,
            "reasoning_effort": "low",
        }
    )

    assert "temperature" not in validated
    assert "max_tokens" not in validated
    assert validated["extra_body"] == {
        "reasoning_effort": "low",
        "max_completion_tokens": 2048,
    }


def test_openai_compatible_validate_no_reasoning_unchanged() -> None:
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://gateway.example.com/v1",
            "api_key": "test-key",
            "model": "gateway-model",
            "max_tokens": 1024,
        }
    )

    # Non-reasoning path must preserve temperature/max_tokens for ordinary
    # OpenAI-compatible gateways (vLLM, LM Studio, etc.).
    assert validated["temperature"] == 0.1
    assert validated["max_tokens"] == 1024
    assert "extra_body" not in validated
    assert "reasoning_effort" not in validated


def test_openai_compatible_adapter_uses_distinct_description_and_icon() -> None:
    metadata = OpenAICompatibleLLMAdapter.get_metadata()

    assert OpenAICompatibleLLMAdapter.get_description() == OPENAI_COMPATIBLE_DESCRIPTION
    assert metadata["description"] == OPENAI_COMPATIBLE_DESCRIPTION
    assert OpenAICompatibleLLMAdapter.get_icon() == (
        "/icons/adapter-icons/OpenAICompatible.png"
    )


def _build_llm_for_record_usage(llm_cls: type) -> object:
    llm = llm_cls.__new__(llm_cls)
    llm._platform_api_key = "platform-key"
    llm.platform_kwargs = {"run_id": "run-1"}
    llm._usage_kwargs = {}
    llm._pending_usage = []
    llm.adapter = MagicMock()
    llm.adapter.get_provider.return_value = "custom_openai"
    return llm


def test_record_usage_uses_reported_prompt_tokens_without_estimating() -> None:
    llm_module = _load_llm_module()
    llm = _build_llm_for_record_usage(llm_module.LLM)

    with (
        patch.object(llm_module.litellm, "token_counter") as mock_token_counter,
        patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)),
    ):
        llm._record_usage(
            model="custom_openai/gateway-model",
            messages=[{"role": "user", "content": "hello"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            llm_api="complete",
        )

    mock_token_counter.assert_not_called()
    assert len(llm._pending_usage) == 1
    assert llm._pending_usage[0]["prompt_tokens"] == 3


def test_record_usage_tolerates_unmapped_models_without_prompt_tokens() -> None:
    llm_module = _load_llm_module()
    llm = _build_llm_for_record_usage(llm_module.LLM)

    with (
        patch.object(
            llm_module.litellm, "token_counter", side_effect=Exception("unmapped")
        ),
        patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)),
        patch.object(llm_module.logger, "warning") as mock_warning,
    ):
        llm._record_usage(
            model="custom_openai/gateway-model",
            messages=[{"role": "user", "content": "hello"}],
            usage={"completion_tokens": 4, "total_tokens": 7},
            llm_api="complete",
        )

    assert len(llm._pending_usage) == 1
    assert llm._pending_usage[0]["prompt_tokens"] == 0
    assert "litellm.token_counter() fallback failed" in mock_warning.call_args.args[0]


def test_record_usage_uses_estimated_prompt_tokens_when_usage_has_none() -> None:
    llm_module = _load_llm_module()
    llm = _build_llm_for_record_usage(llm_module.LLM)

    with (
        patch.object(
            llm_module.litellm, "token_counter", return_value=9
        ) as mock_token_counter,
        patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)),
    ):
        llm._record_usage(
            model="custom_openai/gateway-model",
            messages=[{"role": "user", "content": "hello"}],
            usage={"completion_tokens": 4, "total_tokens": 13},
            llm_api="complete",
        )

    mock_token_counter.assert_called_once()
    assert llm._pending_usage[0]["prompt_tokens"] == 9
