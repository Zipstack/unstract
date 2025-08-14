from typing import Any

from unstract.sdk1.adapters.base1 import AzureOpenAIParameters, BaseAdapter
from unstract.sdk1.adapters.enums import AdapterTypes


class AzureOpenAIEmbeddingAdapter(AzureOpenAIParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "azureopenai|9770f3f6-f8ba-4fa0-bb3a-bef48a00e66f"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "AzureOpenAI",
            "version": "1.0.0",
            "adapter": AzureOpenAIEmbeddingAdapter,
            "description": "AzureOpenAI embedding adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "AzureOpenAI"

    @staticmethod
    def get_description() -> str:
        return "AzureOpenAI LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "azure"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/AzureopenAI.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
