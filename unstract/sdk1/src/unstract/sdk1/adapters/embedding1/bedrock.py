from typing import Any

from unstract.sdk1.adapters.base1 import AWSBedrockEmbeddingParameters, BaseAdapter
from unstract.sdk1.adapters.enums import AdapterTypes


class AWSBedrockEmbeddingAdapter(AWSBedrockEmbeddingParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "bedrock|88199741-8d7e-4e8c-9d92-d76b0dc20c91"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "AWSBedrock",
            "version": "1.0.0",
            "adapter": AWSBedrockEmbeddingAdapter,
            "description": "AWSBedrock embedding adapter",
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "Bedrock"

    @staticmethod
    def get_description() -> str:
        return "AWS Bedrock embedding adapter"

    @staticmethod
    def get_provider() -> str:
        return "bedrock"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Bedrock.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
