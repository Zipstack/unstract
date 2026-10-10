from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, OrcaRouterLLMParameters
from unstract.sdk1.adapters.enums import AdapterTypes

DESCRIPTION = (
    "Adapter for OrcaRouter's OpenAI-compatible model routing gateway "
    "(orcarouter.ai). Supply a model name and your OrcaRouter API key; the "
    "endpoint is preconfigured."
)


class OrcaRouterLLMAdapter(OrcaRouterLLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "orcarouter|cc86ba36-f289-46a9-b60e-b2e8940c4385"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "OrcaRouter",
            "version": "1.0.0",
            "adapter": OrcaRouterLLMAdapter,
            "description": DESCRIPTION,
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "OrcaRouter"

    @staticmethod
    def get_description() -> str:
        return DESCRIPTION

    @staticmethod
    def get_provider() -> str:
        return "orcarouter"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/OrcaRouter.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
