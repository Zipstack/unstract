from typing import Any

from unstract.sdk1.adapters.base1 import BaseAdapter, NvidiaBuildEmbeddingParameters
from unstract.sdk1.adapters.enums import AdapterTypes

DESCRIPTION = (
    "Adapter for NVIDIA's OpenAI-compatible embedding models (build.nvidia.com). "
    "Supply a model name and your NVIDIA API key; the endpoint is preconfigured."
)


class NvidiaBuildEmbeddingAdapter(NvidiaBuildEmbeddingParameters, BaseAdapter):
    @staticmethod
    def get_id() -> str:
        return "nvidiabuild|2afcdf59-5323-4086-97fb-d9a0432e7795"

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        return {
            "name": "NVIDIA Build",
            "version": "1.0.0",
            "adapter": NvidiaBuildEmbeddingAdapter,
            "description": DESCRIPTION,
            "is_active": True,
        }

    @staticmethod
    def get_name() -> str:
        return "NVIDIA Build"

    @staticmethod
    def get_description() -> str:
        return DESCRIPTION

    @staticmethod
    def get_provider() -> str:
        return "nvidia_build"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/NvidiaBuild.png"

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING
