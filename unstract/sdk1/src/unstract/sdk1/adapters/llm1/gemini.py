from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, GeminiLLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes


class GeminiLLMAdapter(GeminiLLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "gemini|085f6c03-b57e-4594-85bb-40e2616c2736"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Gemini",
            "version": "1.0.0",
            "adapter": GeminiLLMAdapter,
            "description": "Google Gemini LLM adapter via Google AI Studio",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Gemini"

    @staticmethod
    def get_description() -> str:
        return "Google Gemini LLM adapter via Google AI Studio"

    @staticmethod
    def get_provider() -> str:
        return "gemini"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Gemini.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
