from typing import Any

from unstract.sdk1.adapters.base1 import AWSBedrockParameters, BaseAdapter
from unstract.sdk1.adapters.enums import AdapterTypes


class AWSBedrockLLMAdapter(AWSBedrockParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "AWSBedrock",
            "version": "1.0.0",
            "adapter": AWSBedrockLLMAdapter,
            "description": "AWSBedrock LLM adapter",
            "is_active": True,
    }

    @staticmethod
    def get_name() -> str:
        return "AWSBedrock"

    @staticmethod
    def get_description() -> str:
        return "AWSBedrock LLM adapter"

    @staticmethod
    def get_provider() -> str:
        return "bedrock"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Bedrock.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.LLM

