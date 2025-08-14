from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, VertexAIParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class VertexAIEmbeddingAdapter(VertexAIParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "vertexai|457a256b-e74f-4251-98a0-8864aafb42a5"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "VertexAI",
            "version": "1.0.0",
            "adapter": VertexAIEmbeddingAdapter,
            "description": "VertexAI embedding adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "VertexAI"

    @staticmethod
    def get_description() -> str:
        return "VertexAI embedding adapter"

    @staticmethod
    def get_provider() -> str:
        return "vertexai"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/VertexAI.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
