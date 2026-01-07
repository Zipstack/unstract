import glob
import inspect
import logging
import os
from abc import ABC, abstractmethod
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from pydantic import BaseModel, Field, model_validator
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.enums import AdapterTypes

logger = logging.getLogger(__name__)


def register_adapters(adapters: dict[str, dict[str, "Any"]], adapter_type: str) -> None:
    """Register all SDK v1 adapters of given type.

    Args:
        adapters: Dictionary to store registered adapters.
        adapter_type: Type of adapter to register.
    """
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
            # However their repr is DIFFERENT from their type, because
            # pydantic is involved.
            # e.g. repr - class unstract.sdk1.adapters.llm1.base.OpenAILLMAdapter
            #      type - class pydantic._internal._model_construction.ModelMetaclass
            #
            # This leads to following matrix for various introspection methods:
            #
            # member type                 | hasattr(obj, "<member_name>") | "<member_name>" in obj.__dict__ | "<member_name>" in obj.__annotations__  # noqa: E501
            # ----------------------------|-------------------------------|---------------------------------|---------------------------------------  # noqa: E501
            # method    (e.g. `get_id`)   | True                          | True                            | False  # noqa: E501
            # attribute (e.g. `metadata`) | False                         | False                           | True  # noqa: E501
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
        schema_path = (
            f"{os.path.dirname(__file__)}/"
            f"{cls.get_adapter_type().name.lower()}1/static/"
            f"{cls.get_provider()}.json"
        )
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
    max_tokens: int | None = None
    max_retries: int | None = None

    @staticmethod
    @abstractmethod
    # NOTE: Apply metadata transformations before provider args validation.
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        pass

    @staticmethod
    @abstractmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        pass


class BaseEmbeddingParameters(BaseModel):
    """Base parameters for all SDK v1 embedding providers."""

    model: str
    timeout: float | int | None = 600
    max_retries: int | None = None

    @staticmethod
    @abstractmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        pass

    @staticmethod
    @abstractmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        pass


class OpenAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/openai/."""

    api_key: str
    api_base: str
    api_version: str | None = None
    reasoning_effort: str | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OpenAILLMParameters.validate_model(adapter_metadata)

        # Handle OpenAI reasoning configuration
        enable_reasoning = adapter_metadata.get("enable_reasoning", False)

        # If enable_reasoning is not explicitly provided but reasoning_effort is present,
        # assume reasoning was enabled in a previous validation
        has_reasoning_effort = (
            "reasoning_effort" in adapter_metadata
            and adapter_metadata.get("reasoning_effort") is not None
        )
        if not enable_reasoning and has_reasoning_effort:
            enable_reasoning = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_reasoning:
            reasoning_effort = adapter_metadata.get("reasoning_effort", "medium")
            result_metadata["reasoning_effort"] = reasoning_effort
            result_metadata["temperature"] = 1

        # Create validation metadata excluding control fields
        exclude_fields = {"enable_reasoning"}
        if not enable_reasoning:
            exclude_fields.add("reasoning_effort")

        validation_metadata = {
            k: v for k, v in result_metadata.items() if k not in exclude_fields
        }

        validated = OpenAILLMParameters(**validation_metadata).model_dump()

        # Clean up result based on reasoning state
        if not enable_reasoning and "reasoning_effort" in validated:
            validated.pop("reasoning_effort")
        elif enable_reasoning:
            validated["reasoning_effort"] = result_metadata.get(
                "reasoning_effort", "medium"
            )

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add openai/ prefix if the model doesn't already have it
        if model.startswith("openai/"):
            return model
        else:
            return f"openai/{model}"


class AzureOpenAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/azure/#completion---using-azure_ad_token-api_base-api_version."""

    api_base: str
    api_version: str | None = None
    api_key: str
    temperature: float | None = 1
    num_retries: int | None = 3
    reasoning_effort: str | None = None

    @model_validator(mode="before")
    @classmethod
    def set_model_from_deployment_name(cls, data: dict[str, "Any"]) -> dict[str, "Any"]:
        """Convert deployment_name to model field before validation."""
        if "deployment_name" in data:
            deployment_name = data.pop("deployment_name")
            if not deployment_name.startswith("azure/"):
                deployment_name = f"azure/{deployment_name}"
            data["model"] = deployment_name
        return data

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AzureOpenAILLMParameters.validate_model(
            adapter_metadata
        )

        # Ensure we have the endpoint in the right format for Azure
        azure_endpoint = adapter_metadata.get("azure_endpoint", "")
        if azure_endpoint:
            adapter_metadata["api_base"] = azure_endpoint

        # Handle Azure OpenAI reasoning configuration
        enable_reasoning = adapter_metadata.get("enable_reasoning", False)

        # If enable_reasoning is not explicitly provided but reasoning_effort is present,
        # assume reasoning was enabled in a previous validation
        has_reasoning_effort = (
            "reasoning_effort" in adapter_metadata
            and adapter_metadata.get("reasoning_effort") is not None
        )
        if not enable_reasoning and has_reasoning_effort:
            enable_reasoning = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_reasoning:
            reasoning_effort = adapter_metadata.get("reasoning_effort", "medium")
            result_metadata["reasoning_effort"] = reasoning_effort
            result_metadata["temperature"] = 1

        # Create validation metadata excluding control fields
        exclude_fields = {"enable_reasoning"}
        if not enable_reasoning:
            exclude_fields.add("reasoning_effort")

        validation_metadata = {
            k: v for k, v in result_metadata.items() if k not in exclude_fields
        }

        validated = AzureOpenAILLMParameters(**validation_metadata).model_dump()

        # Clean up result based on reasoning state
        if not enable_reasoning and "reasoning_effort" in validated:
            validated.pop("reasoning_effort")
        elif enable_reasoning:
            validated["reasoning_effort"] = result_metadata.get(
                "reasoning_effort", "medium"
            )

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        # deployment_name ALWAYS takes precedence over model
        if "deployment_name" in adapter_metadata:
            deployment_name = adapter_metadata["deployment_name"]
            if deployment_name.startswith("azure/"):
                return deployment_name
            return f"azure/{deployment_name}"

        # Only use model if deployment_name doesn't exist (second validation call)
        model = adapter_metadata.get("model", "")
        if model.startswith("azure/"):
            return model
        return f"azure/{model}"


class VertexAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/vertex."""

    vertex_credentials: str
    vertex_project: str
    safety_settings: list[dict[str, str]]

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        # Make a copy so we don't modify the original
        metadata_copy = {**adapter_metadata}

        # Set model with proper prefix
        metadata_copy["model"] = VertexAILLMParameters.validate_model(metadata_copy)

        # Map credentials and project fields
        if "json_credentials" in metadata_copy and not metadata_copy.get(
            "vertex_credentials"
        ):
            metadata_copy["vertex_credentials"] = metadata_copy["json_credentials"]
        if "project" in metadata_copy and not metadata_copy.get("vertex_project"):
            metadata_copy["vertex_project"] = metadata_copy["project"]

        # Handle Vertex AI thinking configuration (for Gemini models)
        enable_thinking = metadata_copy.get("enable_thinking", False)

        # If enable_thinking is not explicitly provided but thinking config is present,
        # assume thinking was enabled in a previous validation
        has_thinking_config = (
            "thinking" in metadata_copy and metadata_copy.get("thinking") is not None
        )
        if not enable_thinking and has_thinking_config:
            enable_thinking = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = metadata_copy.copy()

        if enable_thinking:
            if has_thinking_config:
                # Preserve existing thinking config
                result_metadata["thinking"] = metadata_copy["thinking"]
            else:
                # Create new thinking config for enabled state
                thinking_config = {"type": "enabled"}
                budget_tokens = metadata_copy.get("budget_tokens")
                if budget_tokens is not None:
                    thinking_config["budget_tokens"] = budget_tokens
                result_metadata["thinking"] = thinking_config
                result_metadata["temperature"] = 1
        else:
            # Vertex AI requires explicit disabled state with budget 0
            result_metadata["thinking"] = {"type": "disabled", "budget_tokens": 0}

        # Handle safety settings
        ss_dict = result_metadata.get("safety_settings", {})

        # Handle case where safety_settings is already a list
        if isinstance(ss_dict, list):
            result_metadata["safety_settings"] = ss_dict
        else:
            # Convert dictionary format to list format
            result_metadata["safety_settings"] = [
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
            "max_tokens",
            "max_retries",
            "timeout",
            "temperature",
            "n",
            "stream",
        ]

        # Create validation metadata excluding control fields
        validation_metadata = {
            k: v
            for k, v in result_metadata.items()
            if k not in ("enable_thinking", "budget_tokens", "thinking")
        }

        # First validate using pydantic
        validated_data = VertexAILLMParameters(**validation_metadata).model_dump()

        # Preserve any important fields not in the model
        for field in fields_to_preserve:
            if field in result_metadata and field not in validated_data:
                validated_data[field] = result_metadata[field]

        # Always add thinking config to final result (either enabled or disabled)
        validated_data["thinking"] = result_metadata["thinking"]

        return validated_data

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add vertex_ai/ prefix if the model doesn't already have it
        if model.startswith("vertex_ai/"):
            return model
        else:
            return f"vertex_ai/{model}"


class AWSBedrockLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/bedrock."""

    aws_access_key_id: str | None
    aws_secret_access_key: str | None
    aws_region_name: str | None
    max_retries: int | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AWSBedrockLLMParameters.validate_model(
            adapter_metadata
        )
        if "region_name" in adapter_metadata and not adapter_metadata.get(
            "aws_region_name"
        ):
            adapter_metadata["aws_region_name"] = adapter_metadata["region_name"]

        # Handle AWS Bedrock thinking configuration (for Claude models)
        enable_thinking = adapter_metadata.get("enable_thinking", False)

        # If enable_thinking is not explicitly provided but thinking config is present,
        # assume thinking was enabled in a previous validation
        has_thinking_config = (
            "thinking" in adapter_metadata
            and adapter_metadata.get("thinking") is not None
        )
        if not enable_thinking and has_thinking_config:
            enable_thinking = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_thinking:
            # Set temperature to 1 for thinking mode
            result_metadata["temperature"] = 1

            if has_thinking_config:
                # Preserve existing thinking config
                result_metadata["thinking"] = adapter_metadata["thinking"]
            else:
                # Create new thinking config
                thinking_config = {"type": "enabled"}
                budget_tokens = adapter_metadata.get("budget_tokens")
                if budget_tokens is not None:
                    thinking_config["budget_tokens"] = budget_tokens
                result_metadata["thinking"] = thinking_config
                result_metadata["temperature"] = 1

        # Create validation metadata excluding control fields
        validation_metadata = {
            k: v
            for k, v in result_metadata.items()
            if k not in ("enable_thinking", "budget_tokens", "thinking")
        }

        validated = AWSBedrockLLMParameters(**validation_metadata).model_dump()

        # Add thinking config to final result if enabled
        if enable_thinking and "thinking" in result_metadata:
            validated["thinking"] = result_metadata["thinking"]

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add bedrock/ prefix if the model doesn't already have it
        if model.startswith("bedrock/"):
            return model
        else:
            return f"bedrock/{model}"


class AnthropicLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/anthropic."""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AnthropicLLMParameters.validate_model(
            adapter_metadata
        )

        # Handle Anthropic thinking configuration
        enable_thinking = adapter_metadata.get("enable_thinking", False)

        # If enable_thinking is not explicitly provided but thinking config is present,
        # assume thinking was enabled in a previous validation
        has_thinking_config = (
            "thinking" in adapter_metadata
            and adapter_metadata.get("thinking") is not None
        )
        if not enable_thinking and has_thinking_config:
            enable_thinking = True

        # Handle extended context (1M tokens) configuration
        enable_extended_context = adapter_metadata.get("enable_extended_context", False)

        # If enable_extended_context is not explicitly provided but extra_headers
        # with context-1m is present, assume it was enabled in a previous validation
        extra_headers = adapter_metadata.get("extra_headers", {}) or {}
        anthropic_beta = str(extra_headers.get("anthropic-beta", ""))
        has_extended_context_header = (
            "extra_headers" in adapter_metadata
            and adapter_metadata.get("extra_headers") is not None
            and "anthropic-beta" in extra_headers
            and "context-1m" in anthropic_beta
        )
        if not enable_extended_context and has_extended_context_header:
            enable_extended_context = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_thinking:
            if has_thinking_config:
                # Preserve existing thinking config
                result_metadata["thinking"] = adapter_metadata["thinking"]
            else:
                # Create new thinking config
                thinking_config = {"type": "enabled"}
                budget_tokens = adapter_metadata.get("budget_tokens")
                if budget_tokens is not None:
                    thinking_config["budget_tokens"] = budget_tokens
                result_metadata["thinking"] = thinking_config
                result_metadata["temperature"] = 1

        # Create validation metadata excluding control fields
        exclude_fields = (
            "enable_thinking",
            "budget_tokens",
            "thinking",
            "enable_extended_context",
            "extra_headers",
        )
        validation_metadata = {
            k: v for k, v in result_metadata.items() if k not in exclude_fields
        }

        validated = AnthropicLLMParameters(**validation_metadata).model_dump()

        # Add thinking config to final result if enabled
        if enable_thinking and "thinking" in result_metadata:
            validated["thinking"] = result_metadata["thinking"]

        # Add extra_headers for extended context (1M tokens) if enabled
        if enable_extended_context:
            validated["extra_headers"] = {"anthropic-beta": "context-1m-2025-08-07"}

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add anthropic/ prefix if the model doesn't already have it
        if model.startswith("anthropic/"):
            return model
        else:
            return f"anthropic/{model}"


class AnyscaleLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/anyscale."""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AnyscaleLLMParameters.validate_model(adapter_metadata)

        return AnyscaleLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add anyscale/ prefix if the model doesn't already have it
        if model.startswith("anyscale/"):
            return model
        else:
            return f"anyscale/{model}"


class MistralLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/mistral."""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = MistralLLMParameters.validate_model(adapter_metadata)

        return MistralLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add mistral/ prefix if the model doesn't already have it
        if model.startswith("mistral/"):
            return model
        else:
            return f"mistral/{model}"


class OllamaLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/ollama."""

    api_base: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OllamaLLMParameters.validate_model(adapter_metadata)
        adapter_metadata["api_base"] = adapter_metadata.get("base_url", "")

        return OllamaLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add ollama_chat/ prefix if the model doesn't already have it
        if model.startswith("ollama_chat/"):
            return model
        else:
            return f"ollama_chat/{model}"


# Embedding Parameter Classes


class OpenAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/openai."""

    api_key: str
    api_base: str | None = None
    embed_batch_size: int | None = 10

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OpenAIEmbeddingParameters.validate_model(
            adapter_metadata
        )

        return OpenAIEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        return model


class AzureOpenAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/azure."""

    api_key: str
    api_base: str
    api_version: str | None
    embed_batch_size: int | None = 5
    num_retries: int | None = 3

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AzureOpenAIEmbeddingParameters.validate_model(
            adapter_metadata
        )

        # Ensure we have the endpoint in the right format for Azure
        azure_endpoint = adapter_metadata.get("azure_endpoint", "")
        if azure_endpoint:
            adapter_metadata["api_base"] = azure_endpoint

        # Map num_retries to max_retries for consistency
        if "num_retries" in adapter_metadata and not adapter_metadata.get("max_retries"):
            adapter_metadata["max_retries"] = adapter_metadata["num_retries"]

        return AzureOpenAIEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get(
            "deployment_name", ""
        )  # litellm expects model to be in the format of "azure/<deployment_name>"
        # Only add azure/ prefix if the model doesn't already have it
        if model.startswith("azure/"):
            formatted_model = model
        else:
            formatted_model = f"azure/{model}"
        del adapter_metadata["deployment_name"]
        return formatted_model


class VertexAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/vertex."""

    vertex_credentials: str
    vertex_project: str
    embed_batch_size: int | None = 10
    embed_mode: str | None = "default"

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        # Make a copy so we don't modify the original
        metadata_copy = {**adapter_metadata}

        # Set model with proper prefix
        metadata_copy["model"] = VertexAIEmbeddingParameters.validate_model(metadata_copy)

        # Map credentials and project fields
        if "json_credentials" in metadata_copy and not metadata_copy.get(
            "vertex_credentials"
        ):
            metadata_copy["vertex_credentials"] = metadata_copy["json_credentials"]
        if "project" in metadata_copy and not metadata_copy.get("vertex_project"):
            metadata_copy["vertex_project"] = metadata_copy["project"]

        return VertexAIEmbeddingParameters(**metadata_copy).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        return model


class AWSBedrockEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/bedrock."""

    aws_access_key_id: str | None
    aws_secret_access_key: str | None
    aws_region_name: str | None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AWSBedrockEmbeddingParameters.validate_model(
            adapter_metadata
        )
        if "region_name" in adapter_metadata and not adapter_metadata.get(
            "aws_region_name"
        ):
            adapter_metadata["aws_region_name"] = adapter_metadata["region_name"]

        return AWSBedrockEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        return model


class OllamaEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/ollama."""

    api_base: str
    embed_batch_size: int | None = 10

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OllamaEmbeddingParameters.validate_model(
            adapter_metadata
        )
        adapter_metadata["api_base"] = adapter_metadata.get("base_url", "")

        return OllamaEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model_name", "")
        return model
