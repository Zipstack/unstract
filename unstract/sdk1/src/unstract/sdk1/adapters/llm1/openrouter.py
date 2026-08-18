from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, OpenRouterLLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes

DESCRIPTION = (
    "Adapter for OpenRouter's OpenAI-compatible API (openrouter.ai). "
    "Supply a model name and your OpenRouter API key; the endpoint is preconfigured."
)


class OpenRouterLLMAdapter(OpenRouterLLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "openrouter|17756452-5dca-4e10-9cbf-d9bc16505458"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "OpenRouter",
            "version": "1.0.0",
            "adapter": OpenRouterLLMAdapter,
            "description": DESCRIPTION,
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "OpenRouter"

    @staticmethod
    def get_description() -> str:
        return DESCRIPTION

    @staticmethod
    def get_provider() -> str:
        return "openrouter"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/OpenRouter.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
