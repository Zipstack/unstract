from typing import Any

from unstract.sdk1.adapters.base1 import AzureAIFoundryLLMParameters, BaseAdapter
from unstract.sdk1.adapters.enums import AdapterTypes


class AzureAIFoundryLLMAdapter(AzureAIFoundryLLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "azure_ai_foundry|1ee34560-ea2b-47ac-bfce-ecc4aa5a48cb"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Azure AI Foundry",
            "version": "1.0.0",
            "adapter": AzureAIFoundryLLMAdapter,
            "description": "Azure AI Foundry LLM adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Azure AI Foundry"

    @staticmethod
    def get_description() -> str:
        return "Azure AI Foundry LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "azure_ai_foundry"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/AzureAIFoundry.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
