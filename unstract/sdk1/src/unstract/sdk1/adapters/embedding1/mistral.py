from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, MistralEmbeddingParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class MistralEmbeddingAdapter(MistralEmbeddingParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "mistral|28a9d784-bc33-46a4-804a-436058e1354f"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Mistral",
            "version": "1.0.0",
            "adapter": MistralEmbeddingAdapter,
            "description": "Mistral embedding adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Mistral"

    @staticmethod
    def get_description() -> str:
        return "Mistral embedding adapter"

    @staticmethod
    def get_provider() -> str:
        return "mistral"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Mistral%20AI.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
