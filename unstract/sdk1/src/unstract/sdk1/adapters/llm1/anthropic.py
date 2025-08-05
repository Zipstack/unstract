from typing import Any

from unstract.sdk1.adapters.base1 import AnthropicParameters, BaseAdapter
from unstract.sdk1.adapters.enums import AdapterTypes


class AnthropicLLMAdapter(AnthropicParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
        "name": "Anthropic",
        "version": "1.0.0",
        "adapter": AnthropicLLMAdapter,
        "description": "Anthropic LLM adapter",
        "is_active": True,
    }

    @staticmethod
    def get_name() -> str:
        return "Anthropic"

    @staticmethod
    def get_description() -> str:
        return "Anthropic LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "anthropic"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Anthropic.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM

