from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, OllamaParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class OllamaLLMAdapter(OllamaParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "ollama|4b8bd31a-ce42-48d4-9d69-f29c12e0f276"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Ollama",
            "version": "1.0.0",
            "adapter": OllamaLLMAdapter,
            "description": "Ollama LLM adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Ollama"

    @staticmethod
    def get_description() -> str:
        return "Ollama LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "ollama"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/ollama.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
