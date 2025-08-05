from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, OllamaParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class OllamaEmbeddingAdapter(OllamaParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "ollama|d58d7080-55a9-4542-becd-8433528e127b"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Ollama",
            "version": "1.0.0",
            "adapter": OllamaEmbeddingAdapter,
            "description": "Ollama embedding adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Ollama"

    @staticmethod
    def get_description() -> str:
        return "Ollama embedding adapter"

    @staticmethod
    def get_provider() -> str:
        return "ollama"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/ollama.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING

