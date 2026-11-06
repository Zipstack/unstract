from typing import Any

from unstract.sdk1.adapters.base1 import AtlasCloudLLMParameters, BaseAdapter
from unstract.sdk1.adapters.enums import AdapterTypes

DESCRIPTION = (
    "Adapter for Atlas Cloud's OpenAI-compatible hosted models (atlascloud.ai). "
    "Supply a model name and your Atlas Cloud API key; the endpoint is preconfigured."
)


class AtlasCloudLLMAdapter(AtlasCloudLLMParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "atlascloud|713f36cf-3045-4c7b-8bee-f0f33517f1e5"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "Atlas Cloud",
            "version": "1.0.0",
            "adapter": AtlasCloudLLMAdapter,
            "description": DESCRIPTION,
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Atlas Cloud"

    @staticmethod
    def get_description() -> str:
        return DESCRIPTION

    @staticmethod
    def get_provider() -> str:
        return "atlascloud"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/AtlasCloud.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM
