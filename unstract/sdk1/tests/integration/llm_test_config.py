"""Configuration for LLM adapter integration tests.

This module defines the test configurations for all LLM providers.
Each provider configuration specifies the required environment variables
and adapter metadata structure.
"""

import os
from typing import Any


class LLMProviderConfig:
    """Configuration for a single LLM provider."""

    def __init__(
        self,
        provider_name: str,
        adapter_id: str,
        required_env_vars: list[str],
        metadata_builder: callable,
        skip_reason: str = None,
    ):
        """Initialize provider configuration.

        Args:
            provider_name: Display name of the provider
            adapter_id: Adapter ID string
            required_env_vars: List of required environment variable names
            metadata_builder: Function that builds adapter_metadata from env vars
            skip_reason: Optional custom skip reason
        """
        self.provider_name = provider_name
        self.adapter_id = adapter_id
        self.required_env_vars = required_env_vars
        self.metadata_builder = metadata_builder
        self.skip_reason = skip_reason

    def get_missing_env_vars(self) -> list[str]:
        """Get list of missing required environment variables."""
        return [var for var in self.required_env_vars if not os.getenv(var)]

    def should_skip(self) -> tuple[bool, str]:
        """Check if tests should be skipped for this provider.

        Returns:
            Tuple of (should_skip: bool, reason: str)
        """
        missing_vars = self.get_missing_env_vars()
        if missing_vars:
            reason = (
                f"Required {self.provider_name} environment variables not set: "
                f"{', '.join(missing_vars)}"
            )
            return True, reason
        return False, ""

    def build_metadata(self) -> dict[str, Any]:
        """Build adapter metadata from environment variables."""
        return self.metadata_builder()


# Metadata builder functions for each provider
def build_openai_metadata() -> dict[str, Any]:
    """Build OpenAI adapter metadata."""
    return {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "api_key": os.getenv("OPENAI_API_KEY"),
        "api_base": os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }


def build_anthropic_metadata() -> dict[str, Any]:
    """Build Anthropic adapter metadata."""
    return {
        "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }


def build_azure_openai_metadata() -> dict[str, Any]:
    """Build Azure OpenAI adapter metadata."""
    return {
        "model": os.getenv("AZURE_OPENAI_MODEL"),
        "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
        "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }


def build_bedrock_metadata() -> dict[str, Any]:
    """Build AWS Bedrock adapter metadata."""
    return {
        "model": os.getenv("BEDROCK_MODEL"),
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region_name": os.getenv("AWS_REGION_NAME"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }


def build_vertexai_metadata() -> dict[str, Any]:
    """Build Vertex AI adapter metadata."""
    return {
        "model": os.getenv("VERTEXAI_MODEL"),
        "json_credentials": os.getenv("VERTEXAI_JSON_CREDENTIALS"),
        "project": os.getenv("VERTEXAI_PROJECT"),
        "temperature": 0.1,
        "max_tokens": 1000,
        "safety_settings": {
            "harassment": "BLOCK_ONLY_HIGH",
            "hate_speech": "BLOCK_ONLY_HIGH",
            "sexual_content": "BLOCK_ONLY_HIGH",
            "dangerous_content": "BLOCK_ONLY_HIGH",
            "civic_integrity": "BLOCK_ONLY_HIGH",
        },
    }


def build_ollama_metadata() -> dict[str, Any]:
    """Build Ollama adapter metadata."""
    return {
        "model": os.getenv("OLLAMA_MODEL"),
        "base_url": os.getenv("OLLAMA_BASE_URL"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }


def build_mistral_metadata() -> dict[str, Any]:
    """Build Mistral AI adapter metadata."""
    return {
        "model": os.getenv("MISTRAL_MODEL"),
        "api_key": os.getenv("MISTRAL_API_KEY"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }


def build_anyscale_metadata() -> dict[str, Any]:
    """Build Anyscale adapter metadata."""
    return {
        "model": os.getenv("ANYSCALE_MODEL"),
        "api_key": os.getenv("ANYSCALE_API_KEY"),
        "temperature": 0.1,
        "max_tokens": 1000,
    }


# Provider configurations
PROVIDER_CONFIGS = {
    "openai": LLMProviderConfig(
        provider_name="OpenAI",
        adapter_id="openai|502ecf49-e47c-445c-9907-6d4b90c5cd17",
        required_env_vars=["OPENAI_API_KEY", "OPENAI_MODEL"],
        metadata_builder=build_openai_metadata,
    ),
    "anthropic": LLMProviderConfig(
        provider_name="Anthropic",
        adapter_id="anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203",
        required_env_vars=["ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"],
        metadata_builder=build_anthropic_metadata,
    ),
    "azure_openai": LLMProviderConfig(
        provider_name="Azure OpenAI",
        adapter_id="azureopenai|592d84b9-fe03-4102-a17e-6b391f32850b",
        required_env_vars=[
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_MODEL",
        ],
        metadata_builder=build_azure_openai_metadata,
    ),
    "bedrock": LLMProviderConfig(
        provider_name="AWS Bedrock",
        adapter_id="bedrock|8d18571f-5e96-4505-bd28-ad0379c64064",
        required_env_vars=[
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION_NAME",
            "BEDROCK_MODEL",
        ],
        metadata_builder=build_bedrock_metadata,
    ),
    "vertexai": LLMProviderConfig(
        provider_name="Vertex AI",
        adapter_id="vertexai|3a98b2e4-8f91-4d2e-b156-739c6f3d8a45",
        required_env_vars=[
            "VERTEXAI_PROJECT",
            "VERTEXAI_JSON_CREDENTIALS",
            "VERTEXAI_MODEL",
        ],
        metadata_builder=build_vertexai_metadata,
    ),
    "ollama": LLMProviderConfig(
        provider_name="Ollama",
        adapter_id="ollama|ae8a2e19-4f77-4c3e-bf92-6c2d6a8e5f23",
        required_env_vars=["OLLAMA_BASE_URL", "OLLAMA_MODEL"],
        metadata_builder=build_ollama_metadata,
    ),
    "mistral": LLMProviderConfig(
        provider_name="Mistral AI",
        adapter_id="mistral|7b9e2f1c-4a3d-4e8f-b567-8c9d1e2f3a45",
        required_env_vars=["MISTRAL_API_KEY", "MISTRAL_MODEL"],
        metadata_builder=build_mistral_metadata,
    ),
    "anyscale": LLMProviderConfig(
        provider_name="Anyscale",
        adapter_id="anyscale|6c8d3e2f-5a4b-4f9e-a789-1d2e3f4a5b6c",
        required_env_vars=["ANYSCALE_API_KEY", "ANYSCALE_MODEL"],
        metadata_builder=build_anyscale_metadata,
    ),
}


def get_available_providers() -> list[str]:
    """Get list of providers that have required environment variables set.

    Returns:
        List of provider keys that can be tested
    """
    available = []
    for provider_key, config in PROVIDER_CONFIGS.items():
        should_skip, _ = config.should_skip()
        if not should_skip:
            available.append(provider_key)
    return available


def get_provider_config(provider_key: str) -> LLMProviderConfig:
    """Get provider configuration by key.

    Args:
        provider_key: Provider key (e.g., 'openai', 'anthropic')

    Returns:
        Provider configuration

    Raises:
        KeyError: If provider key is not found
    """
    return PROVIDER_CONFIGS[provider_key]
