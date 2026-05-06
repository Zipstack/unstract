import os
from typing import Any, ClassVar

from unstract.sdk1.adapters.base1 import BaseAdapter, OpenAICompatibleLLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes

DESCRIPTION = (
    "Adapter for servers that implement the OpenAI Chat Completions API "
    "(vLLM, LM Studio, self-hosted gateways, and third-party providers). "
    "Use OpenAI for the official OpenAI service."
)


class OpenAICompatibleLLMAdapter(OpenAICompatibleLLMParameters, BaseAdapter):
    SCHEMA_PATH: ClassVar[str] = os.path.join(
        os.path.dirname(__file__), "static", "openai_compatible.json"
    )

    @staticmethod
    def get_id() -> str:
        return "openaicompatible|b6d10f33-2c41-49fc-a8c2-58d2b247fc09"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "OpenAI Compatible",
            "version": "1.0.0",
            "adapter": OpenAICompatibleLLMAdapter,
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
        return AdapterTypes.LLM
