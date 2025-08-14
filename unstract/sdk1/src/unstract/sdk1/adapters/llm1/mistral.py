from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, MistralParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class MistralLLMAdapter(MistralParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "mistral|00f766a5-6d6d-47ea-9f6c-ddb1e8a94e82"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Mistral",
            "version": "1.0.0",
            "adapter": MistralLLMAdapter,
            "description": "Mistral LLM adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Mistral"

    @staticmethod
    def get_description() -> str:
        return "Mistral LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "mistral"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Mistral%20AI.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
