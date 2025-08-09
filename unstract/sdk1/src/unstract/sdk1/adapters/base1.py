import glob
import inspect
import os
import sys
from abc import ABC, abstractmethod
from importlib import import_module
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.enums import AdapterTypes


def register_adapters(adapters: dict[str, dict[str, Any]], adapter_type: str):
    """Register all SDK v1 adapters of given type."""

    adapter_type = adapter_type.lower()
    adapter_type_ver = adapter_type + "1"  # e.g. embedding1, llm1, etc

    cwd = os.path.dirname(os.path.abspath(__file__))
    adapter_dir = os.path.join(cwd, adapter_type_ver)
    py_files = [file for file in glob.glob(os.path.join(adapter_dir, "*.py")) if not file.startswith('__')]

    for py_file in py_files:
        file_name_w_ext = os.path.basename(py_file)
        file_name, ext = os.path.splitext(file_name_w_ext)
        module_name = f"unstract.sdk1.adapters.{adapter_type_ver}.{file_name}"

        for name, obj in inspect.getmembers(import_module(module_name)):
            if name.startswith("__"):
                continue
            if not name.lower().endswith(f"{adapter_type}adapter"):
                continue
            if not inspect.isclass(obj) or obj.__module__ != module_name:
                continue

            # IMPORTANT!
            # 
            # We are introspecting adapter classes to retrieve id and metadata.
            # However their `repr`` is DIFFERENT from their `type`, because `pydantic` is involved.
            # e.g. repr: <class 'unstract.sdk1.adapters.llm1.base.OpenAILLMAdapter'>
            #      type: <class 'pydantic._internal._model_construction.ModelMetaclass'>
            # 
            # This leads to following matrix for various introspection methods:
            # 
            # member type                 | hasattr(obj, "<member_name>") | "<member_name>" in obj.__dict__ | "<member_name>" in obj.__annotations__
            # ----------------------------|-------------------------------|---------------------------------|---------------------------------------
            # method    (e.g. `get_id`)   | True                          | True                            | False
            # attribute (e.g. `metadata`) | False                         | False                           | True
            if hasattr(obj, Common.ADAPTER_ID_GETTER) and hasattr(obj, Common.ADAPTER_METADATA_GETTER):
                adapter_id = getattr(obj, Common.ADAPTER_ID_GETTER)()
                metadata = getattr(obj, Common.ADAPTER_METADATA_GETTER)()

                adapters[adapter_id] = {
                    Common.MODULE: metadata[Common.ADAPTER],
                    Common.METADATA: metadata
                }

class BaseAdapter(ABC):
    """Adapter base class for compatibility with all SDK v1 providers."""

    @staticmethod
    @abstractmethod
    def get_id() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_name() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_description() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_provider() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_icon() -> str:
        pass

    @classmethod
    def get_json_schema(cls) -> str:
        schema_path = f"{os.path.dirname(__file__)}/{cls.get_adapter_type().name.lower()}1/static/{cls.get_provider()}.json"
        with open(schema_path) as f:
            return f.read()

    @staticmethod
    @abstractmethod
    def get_adapter_type() -> AdapterTypes:
        pass

class BaseParameters(BaseModel):
    """ Base parameters for all SDK v1 providers.
        See https://docs.litellm.ai/docs/completion/input#input-params-1
    """
    model: str
    # The sampling temperature to be used, between 0 and 2.
    temperature: Optional[float] = Field(default=0.1, ge=0, le=2)
    # The number of chat completion choices to generate for each input message.
    n: Optional[int] = 1
    timeout: Optional[Union[float, int]] = 600
    stream: Optional[bool] = False
    max_tokens: Optional[int] = None
    num_retries: Optional[int] = None

    @staticmethod
    @abstractmethod
    # NOTE: Apply metadata transformations before provider args validation.
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        pass

    @staticmethod
    @abstractmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        pass

class OpenAIParameters(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/openai/"""
    api_key: str
    api_base: str
    api_version: Optional[str] = None

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = OpenAIParameters.validate_model(adapter_metadata)

        return OpenAIParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        return f"openai/{adapter_metadata.get('model', '')}"

class AzureOpenAIParameters(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/azure/#completion---using-azure_ad_token-api_base-api_version"""
    api_base: str
    api_version: Optional[str] = None
    api_key: str
    temperature: Optional[float] = 1

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AzureOpenAIParameters.validate_model(adapter_metadata)
        adapter_metadata["api_base"] = adapter_metadata.get('azure_endpoint', '').split("?")[0]

        return AzureOpenAIParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        return f"azure/{adapter_metadata.get('model', '')}"

class VertexAIParameters(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/vertex"""
    vertex_credentials: str
    vertex_project: str
    safety_settings: list[dict[str, str]]

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = VertexAIParameters.validate_model(adapter_metadata)
        adapter_metadata["vertex_credentials"] = adapter_metadata.get('json_credentials', '')
        adapter_metadata["vertex_project"] = adapter_metadata.get('project', '')

        ss_dict = adapter_metadata.get('safety_settings', {})
        adapter_metadata["safety_settings"] = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": ss_dict.get('harassment', 'BLOCK_ONLY_HIGH')
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": ss_dict.get('hate_speech', 'BLOCK_ONLY_HIGH')
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": ss_dict.get('sexual_content', 'BLOCK_ONLY_HIGH')
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": ss_dict.get('dangerous_content', 'BLOCK_ONLY_HIGH')
            },
            {
                "category": "HARM_CATEGORY_CIVIC_INTEGRITY",
                "threshold": ss_dict.get('civic_integrity', 'BLOCK_ONLY_HIGH')
            },
        ]

        return VertexAIParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        return f"vertex_ai/{adapter_metadata.get('model', '')}"

class AWSBedrockParameters(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/bedrock"""
    aws_access_key_id: Optional[str]
    aws_secret_access_key: Optional[str]
    aws_region_name: Optional[str]

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AWSBedrockParameters.validate_model(adapter_metadata)
        adapter_metadata["aws_region_name"] = adapter_metadata.get('region_name', '')

        return AWSBedrockParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        return f"bedrock/{adapter_metadata.get('model', '')}"

class AnthropicParameters(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/anthropic"""
    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AnthropicParameters.validate_model(adapter_metadata)

        return AnthropicParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        return f"anthropic/{adapter_metadata.get('model', '')}"

class AnyscaleParameters(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/anyscale"""
    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AnyscaleParameters.validate_model(adapter_metadata)

        return AnyscaleParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        return f"anyscale/{adapter_metadata.get('model', '')}"

class MistralParameters(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/mistral"""
    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = MistralParameters.validate_model(adapter_metadata)

        return MistralParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        return f"mistral/{adapter_metadata.get('model', '')}"

class OllamaParameters(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/ollama"""
    api_base: str

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = OllamaParameters.validate_model(adapter_metadata)
        # adapter_metadata["api_base"] = adapter_metadata.get("base_url", "")

        return OllamaParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        return f"ollama_chat/{adapter_metadata.get('model', '')}"
