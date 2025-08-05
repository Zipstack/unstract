from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, OpenAIParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class OpenAILLMAdapter(OpenAIParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "OpenAI",
            "version": "1.0.0",
            "adapter": OpenAILLMAdapter,
            "description": "OpenAI LLM adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "OpenAI"

    @staticmethod
    def get_description() -> str:
        return "OpenAI LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "openai"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/OpenAI.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
