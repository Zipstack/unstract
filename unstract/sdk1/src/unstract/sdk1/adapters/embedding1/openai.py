
from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, OpenAIParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class OpenAIEmbeddingAdapter(OpenAIParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "OpenAI",
            "version": "1.0.0",
            "adapter": OpenAIEmbeddingAdapter,
            "description": "OpenAI embedding adapter",
            "is_active": True,
    }

    @staticmethod
    def get_name() -> str:
        return "OpenAI"

    @staticmethod
    def get_description() -> str:
        return "OpenAI embedding adapter"

    @staticmethod
    def get_provider() -> str:
        return "openai"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/OpenAI.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
