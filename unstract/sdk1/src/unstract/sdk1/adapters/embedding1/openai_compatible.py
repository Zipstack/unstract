from typing import Any

from unstract.sdk1.adapters.base1 import (
    BaseAdapter,
    OpenAICompatibleEmbeddingParameters,
)
from unstract.sdk1.adapters.enums import AdapterTypes

DESCRIPTION = (
    "Embedding adapter for servers that implement the OpenAI Embeddings API "
    "(vLLM, self-hosted gateways, and third-party providers). "
    "Use OpenAI for the official OpenAI service."
)


class OpenAICompatibleEmbeddingAdapter(OpenAICompatibleEmbeddingParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "openaicompatible|65573de7-2ea5-4631-bb49-492717972455"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "OpenAI Compatible",
            "version": "1.0.0",
            "adapter": OpenAICompatibleEmbeddingAdapter,
            "description": DESCRIPTION,
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "OpenAI Compatible"

    @staticmethod
    def get_description() -> str:
        return DESCRIPTION

    @staticmethod
    def get_provider() -> str:
        return "custom_openai"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/OpenAICompatible.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
