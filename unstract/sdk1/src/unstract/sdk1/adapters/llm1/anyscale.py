from typing import Any

from unstract.sdk1.adapters.base1 import AnyscaleParameters, BaseAdapter
from unstract.sdk1.adapters.enums import AdapterTypes


class AnyscaleLLMAdapter(AnyscaleParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "anyscale|adec9815-eabc-4207-9389-79cb89952639"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Anyscale",
            "version": "1.0.0",
            "adapter": AnyscaleLLMAdapter,
            "description": "Anyscale LLM adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Anyscale"

    @staticmethod
    def get_description() -> str:
        return "Anyscale LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "anyscale"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/anyscale.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
