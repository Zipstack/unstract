from unittest.mock import MagicMock, patch

from unstract.sdk1.adapters.base1 import OpenAICompatibleLLMParameters
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.llm1 import adapters
from unstract.sdk1.adapters.llm1.openai_compatible import OpenAICompatibleLLMAdapter


def test_openai_compatible_adapter_is_registered() -> None:
    adapter_id = OpenAICompatibleLLMAdapter.get_id()

    assert adapter_id in adapters
    assert adapters[adapter_id][Common.MODULE] is OpenAICompatibleLLMAdapter


def test_openai_compatible_validate_prefixes_model() -> None:
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://gateway.example.com/v1",
            "api_key": "test-key",
            "model": "qwen-max",
        }
    )

    assert validated["model"] == "custom_openai/qwen-max"


def test_openai_compatible_validate_preserves_prefixed_model() -> None:
    validated = OpenAICompatibleLLMParameters.validate(
        {
            "api_base": "https://gateway.example.com/v1",
            "model": "custom_openai/openai/gpt-4o",
        }
    )

    assert validated["model"] == "custom_openai/openai/gpt-4o"
    assert validated["api_key"] is None


def test_openai_compatible_schema_is_loadable() -> None:
    schema = OpenAICompatibleLLMAdapter.get_json_schema()

    assert "\"title\": \"OpenAI Compatible LLM\"" in schema


def test_record_usage_tolerates_unmapped_models() -> None:
    import sys
    from types import ModuleType

    sys.modules.setdefault("magic", ModuleType("magic"))

    from unstract.sdk1.llm import LLM

    llm = LLM.__new__(LLM)
    llm._platform_api_key = "platform-key"
    llm.platform_kwargs = {"run_id": "run-1"}
    llm.adapter = MagicMock()
    llm.adapter.get_provider.return_value = "custom_openai"

    with (
        patch("unstract.sdk1.llm.token_counter", side_effect=Exception("unmapped")),
        patch("unstract.sdk1.llm.Audit") as mock_audit,
    ):
        llm._record_usage(
            model="custom_openai/qwen-max",
            messages=[{"role": "user", "content": "hello"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            llm_api="complete",
        )

    mock_audit.return_value.push_usage_data.assert_called_once()
