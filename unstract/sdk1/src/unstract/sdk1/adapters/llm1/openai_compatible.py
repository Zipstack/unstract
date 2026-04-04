from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, OpenAICompatibleLLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class OpenAICompatibleLLMAdapter(OpenAICompatibleLLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "openaicompatible|b6d10f33-2c41-49fc-a8c2-58d2b247fc09"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "OpenAI Compatible",
            "version": "1.0.0",
            "adapter": OpenAICompatibleLLMAdapter,
            "description": "OpenAI-compatible LLM adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "OpenAI Compatible"

    @staticmethod
    def get_description() -> str:
        return "OpenAI-compatible LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "custom_openai"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/OpenAI.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
