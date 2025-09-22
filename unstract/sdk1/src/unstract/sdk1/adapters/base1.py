import glob
import inspect
import logging
import os
from abc import ABC, abstractmethod
from importlib import import_module
from typing import Any

from pydantic import BaseModel, Field
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.enums import AdapterTypes

logger = logging.getLogger(__name__)


def register_adapters(adapters: dict[str, dict[str, Any]], adapter_type: str):
    """Register all SDK v1 adapters of given type."""
    adapter_type = adapter_type.lower()
    adapter_type_ver = adapter_type + "1"  # e.g. embedding1, llm1, etc

    cwd = os.path.dirname(os.path.abspath(__file__))
    adapter_dir = os.path.join(cwd, adapter_type_ver)
    py_files = [
        file
        for file in glob.glob(os.path.join(adapter_dir, "*.py"))
        if not file.startswith("__")
    ]

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
            if hasattr(obj, Common.ADAPTER_ID_GETTER) and hasattr(
                obj, Common.ADAPTER_METADATA_GETTER
            ):
                adapter_id = getattr(obj, Common.ADAPTER_ID_GETTER)()
                metadata = getattr(obj, Common.ADAPTER_METADATA_GETTER)()

                adapters[adapter_id] = {
                    Common.MODULE: metadata[Common.ADAPTER],
                    Common.METADATA: metadata,
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


class BaseChatCompletionParameters(BaseModel):
    """Base parameters for all SDK v1 providers.
    See https://docs.litellm.ai/docs/completion/input#input-params-1
    """

    model: str
    # The sampling temperature to be used, between 0 and 2.
    temperature: float | None = Field(default=0.1, ge=0, le=2)
    # The number of chat completion choices to generate for each input message.
    n: int | None = 1
    timeout: float | int | None = 600
    stream: bool | None = False
    max_tokens: int | None = None
    max_retries: int | None = None

    @staticmethod
    @abstractmethod
    # NOTE: Apply metadata transformations before provider args validation.
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        pass

    @staticmethod
    @abstractmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        pass

class BaseEmbeddingParameters(BaseModel):
    """Base parameters for all SDK v1 embedding providers."""

    model: str
    timeout: float | int | None = 600
    max_retries: int | None = None

    @staticmethod
    @abstractmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        pass

    @staticmethod
    @abstractmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        pass

class OpenAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/openai/"""

    api_key: str
    api_base: str
    api_version: str | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = OpenAILLMParameters.validate_model(adapter_metadata)

        return OpenAILLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return f"openai/{model}" if "/" not in model else model


class AzureOpenAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/azure/#completion---using-azure_ad_token-api_base-api_version"""

    api_base: str
    api_version: str | None = None
    api_key: str
    temperature: float | None = 1
    num_retries: int | None = 3

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AzureOpenAILLMParameters.validate_model(adapter_metadata)

        # Ensure we have the endpoint in the right format for Azure
        azure_endpoint = adapter_metadata.get("azure_endpoint", "")
        if azure_endpoint:
            adapter_metadata["api_base"] = azure_endpoint
        return AzureOpenAILLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return f"azure/{model}" if "/" not in model else model


class VertexAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/vertex"""

    vertex_credentials: str
    vertex_project: str
    safety_settings: list[dict[str, str]]

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        # Make a copy so we don't modify the original
        metadata_copy = {**adapter_metadata}
        
        # Set model with proper prefix
        metadata_copy["model"] = VertexAILLMParameters.validate_model(metadata_copy)
        
        # Map credentials and project fields
        if "json_credentials" in metadata_copy and not metadata_copy.get("vertex_credentials"):
            metadata_copy["vertex_credentials"] = metadata_copy["json_credentials"]
        if "project" in metadata_copy and not metadata_copy.get("vertex_project"):
            metadata_copy["vertex_project"] = metadata_copy["project"]
        
        # Handle safety settings
        ss_dict = metadata_copy.get("safety_settings", {})
        
        # Handle case where safety_settings is already a list
        if isinstance(ss_dict, list):
            metadata_copy["safety_settings"] = ss_dict
        else:
            # Convert dictionary format to list format
            metadata_copy["safety_settings"] = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": ss_dict.get("harassment", "BLOCK_ONLY_HIGH"),
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": ss_dict.get("hate_speech", "BLOCK_ONLY_HIGH"),
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": ss_dict.get("sexual_content", "BLOCK_ONLY_HIGH"),
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": ss_dict.get("dangerous_content", "BLOCK_ONLY_HIGH"),
                },
                {
                    "category": "HARM_CATEGORY_CIVIC_INTEGRITY",
                    "threshold": ss_dict.get("civic_integrity", "BLOCK_ONLY_HIGH"),
                },
            ]

        # These are the fields to preserve (in addition to model fields)
        fields_to_preserve = [
            "max_tokens", "max_retries", "timeout", "temperature", "n", "stream"
        ]
        
        # First validate using pydantic
        validated_data = VertexAILLMParameters(**metadata_copy).model_dump()
        
        # Preserve any important fields not in the model
        for field in fields_to_preserve:
            if field in metadata_copy and field not in validated_data:
                validated_data[field] = metadata_copy[field]
                
        return validated_data

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return f"vertex_ai/{model}" if "/" not in model else model


class AWSBedrockLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/bedrock"""

    aws_access_key_id: str | None
    aws_secret_access_key: str | None
    aws_region_name: str | None
    max_retries: int | None

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AWSBedrockLLMParameters.validate_model(adapter_metadata)
        if "region_name" in adapter_metadata and not adapter_metadata.get(
            "aws_region_name"
        ):
            adapter_metadata["aws_region_name"] = adapter_metadata["region_name"]

        # Apply AWS Bedrock specific thinking logic
        enable_thinking = adapter_metadata.get("enable_thinking", False)
        if enable_thinking:
            # Set temperature to 1 for thinking mode
            adapter_metadata["temperature"] = 1

            # Add additionalModelRequestFields for thinking
            thinking = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": adapter_metadata.get("budget_tokens", None),
                }
            }
            adapter_metadata.update(thinking)
            adapter_metadata.pop("enable_thinking")
            adapter_metadata.pop("budget_tokens")

        return AWSBedrockLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return f"bedrock/{model}" if "/" not in model else model


class AnthropicLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/anthropic"""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AnthropicLLMParameters.validate_model(adapter_metadata)

        return AnthropicLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return f"anthropic/{model}" if "/" not in model else model


class AnyscaleLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/anyscale"""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AnyscaleLLMParameters.validate_model(adapter_metadata)

        return AnyscaleLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return f"anyscale/{model}" if "/" not in model else model


class MistralLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/mistral"""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = MistralLLMParameters.validate_model(adapter_metadata)

        return MistralLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return f"mistral/{model}" if "/" not in model else model


class OllamaLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/ollama"""

    api_base: str

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = OllamaLLMParameters.validate_model(adapter_metadata)
        adapter_metadata["api_base"] = adapter_metadata.get("base_url", "")

        return OllamaLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return f"ollama_chat/{model}" if "/" not in model else model


# Embedding Parameter Classes

class OpenAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/openai"""

    api_key: str
    api_base: str | None = None
    embed_batch_size: int | None = 10

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = OpenAIEmbeddingParameters.validate_model(adapter_metadata)

        return OpenAIEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return model


class AzureOpenAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/azure"""

    api_key: str
    api_base: str
    api_version: str | None
    embed_batch_size: int | None = 5
    num_retries: int | None = 3

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AzureOpenAIEmbeddingParameters.validate_model(adapter_metadata)

        # Ensure we have the endpoint in the right format for Azure
        azure_endpoint = adapter_metadata.get("azure_endpoint", "")
        if azure_endpoint:
            adapter_metadata["api_base"] = azure_endpoint
    
        # Map num_retries to max_retries for consistency
        if "num_retries" in adapter_metadata and not adapter_metadata.get("max_retries"):
            adapter_metadata["max_retries"] = adapter_metadata["num_retries"]

        return AzureOpenAIEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("deployment_name", "") #litellm expects model to be in the format of "azure/<deployment_namke>"
        model = f"azure/{model}" if "/" not in model else model
        del adapter_metadata["deployment_name"]
        return model


class VertexAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/vertex"""

    vertex_credentials: str
    vertex_project: str
    embed_batch_size: int | None = 10
    embed_mode: str | None = "default"

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        # Make a copy so we don't modify the original
        metadata_copy = {**adapter_metadata}
        
        # Set model with proper prefix
        metadata_copy["model"] = VertexAIEmbeddingParameters.validate_model(metadata_copy)
        
        # Map credentials and project fields
        if "json_credentials" in metadata_copy and not metadata_copy.get("vertex_credentials"):
            metadata_copy["vertex_credentials"] = metadata_copy["json_credentials"]
        if "project" in metadata_copy and not metadata_copy.get("vertex_project"):
            metadata_copy["vertex_project"] = metadata_copy["project"]

        return VertexAIEmbeddingParameters(**metadata_copy).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return model


class AWSBedrockEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/bedrock"""

    aws_access_key_id: str | None
    aws_secret_access_key: str | None
    aws_region_name: str | None

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = AWSBedrockEmbeddingParameters.validate_model(adapter_metadata)
        if "region_name" in adapter_metadata and not adapter_metadata.get("aws_region_name"):
            adapter_metadata["aws_region_name"] = adapter_metadata["region_name"]

        return AWSBedrockEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model", "")
        return model


class OllamaEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/ollama"""

    api_base: str
    embed_batch_size: int | None = 10

    @staticmethod
    def validate(adapter_metadata: dict[str, Any]) -> dict[str, Any]:
        adapter_metadata["model"] = OllamaEmbeddingParameters.validate_model(adapter_metadata)
        adapter_metadata["api_base"] = adapter_metadata.get("base_url", "")

        return OllamaEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, Any]) -> str:
        model = adapter_metadata.get("model_name", "")
        return model
