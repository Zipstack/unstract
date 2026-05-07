from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, GeminiEmbeddingParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class GeminiEmbeddingAdapter(GeminiEmbeddingParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "gemini|5c2a36b8-0b8e-4f26-82c0-9f3b564cb066"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Gemini",
            "version": "1.0.0",
            "adapter": GeminiEmbeddingAdapter,
            "description": "Gemini embedding adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Gemini"

    @staticmethod
    def get_description() -> str:
        return "Gemini embedding adapter"

    @staticmethod
    def get_provider() -> str:
        return "gemini"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Gemini.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
