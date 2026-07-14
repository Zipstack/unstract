from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, MiniMaxLLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes

DESCRIPTION = (
    "Adapter for MiniMax's OpenAI- and Anthropic-compatible APIs. "
    "Supply a model name and your MiniMax API key; the endpoint is preconfigured."
)


class MiniMaxLLMAdapter(MiniMaxLLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "minimax|4f0e4241-2430-4921-81bf-8b2c6040d8d2"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "MiniMax",
            "version": "1.0.0",
            "adapter": MiniMaxLLMAdapter,
            "description": DESCRIPTION,
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "MiniMax"

    @staticmethod
    def get_description() -> str:
        return DESCRIPTION

    @staticmethod
    def get_provider() -> str:
        return "minimax"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/MiniMax.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
