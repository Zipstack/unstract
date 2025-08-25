from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, VertexAILLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class VertexAILLMAdapter(VertexAILLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "vertexai|78fa17a5-a619-47d4-ac6e-3fc1698fdb55"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        """Compatibility layer for SDK v0.

        Returns adapter metadata dict for hooking into other subsystems in the platform
        """
        return {
            "name": "VertexAI",
            "version": "1.0.0",
            "adapter": VertexAILLMAdapter,
            "description": "VertexAI LLM adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "VertexAI"

    @staticmethod
    def get_description() -> str:
        return "VertexAI LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "vertex_ai"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/VertexAI.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
