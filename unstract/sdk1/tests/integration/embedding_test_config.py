"""Configuration for Embedding adapter integration tests.

This module defines the test configurations for all embedding providers.
Each provider configuration specifies the required environment variables
and adapter metadata structure.
"""

import os
from typing import Any


class EmbeddingProviderConfig:
    """Configuration for a single embedding provider."""

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
def build_openai_embedding_metadata() -> dict[str, Any]:
    """Build OpenAI embedding adapter metadata."""
    return {
        "model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        "api_key": os.getenv("OPENAI_EMBEDDING_API_KEY"),
        "api_base": os.getenv("OPENAI_EMBEDDING_API_BASE", "https://api.openai.com/v1"),
        "temperature": 0.0,
    }


def build_azure_openai_embedding_metadata() -> dict[str, Any]:
    """Build Azure OpenAI embedding adapter metadata."""
    return {
        "model": os.getenv("AZURE_OPENAI_EMBEDDING_MODEL"),
        "deployment_name": os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"),
        "api_key": os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY"),
        "azure_endpoint": os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
        "api_version": os.getenv(
            "AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-15-preview"
        ),
        "temperature": 0.0,
    }


def build_bedrock_embedding_metadata() -> dict[str, Any]:
    """Build AWS Bedrock embedding adapter metadata."""
    return {
        "model": os.getenv("BEDROCK_EMBEDDING_MODEL"),
        "aws_access_key_id": os.getenv("AWS_EMBEDDING_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.getenv("AWS_EMBEDDING_SECRET_ACCESS_KEY"),
        "region_name": os.getenv("AWS_EMBEDDING_REGION_NAME"),
        "temperature": 0.0,
    }


def build_vertexai_embedding_metadata() -> dict[str, Any]:
    """Build Vertex AI embedding adapter metadata."""
    return {
        "model": os.getenv("VERTEXAI_EMBEDDING_MODEL"),
        "json_credentials": os.getenv("VERTEXAI_EMBEDDING_JSON_CREDENTIALS"),
        "project": os.getenv("VERTEXAI_EMBEDDING_PROJECT"),
        "temperature": 0.0,
    }


def build_ollama_embedding_metadata() -> dict[str, Any]:
    """Build Ollama embedding adapter metadata."""
    return {
        "model": os.getenv("OLLAMA_EMBEDDING_MODEL"),
        "base_url": os.getenv("OLLAMA_EMBEDDING_BASE_URL"),
        "temperature": 0.0,
    }


# Provider configurations
PROVIDER_CONFIGS = {
    "openai": EmbeddingProviderConfig(
        provider_name="OpenAI",
        adapter_id="openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151",
        required_env_vars=["OPENAI_EMBEDDING_API_KEY", "OPENAI_EMBEDDING_MODEL"],
        metadata_builder=build_openai_embedding_metadata,
    ),
    "azure_openai": EmbeddingProviderConfig(
        provider_name="Azure OpenAI",
        adapter_id="azureopenai|9770f3f6-f8ba-4fa0-bb3a-bef48a00e66f",
        required_env_vars=[
            "AZURE_OPENAI_EMBEDDING_API_KEY",
            "AZURE_OPENAI_EMBEDDING_ENDPOINT",
            "AZURE_OPENAI_EMBEDDING_MODEL",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",
        ],
        metadata_builder=build_azure_openai_embedding_metadata,
    ),
    "bedrock": EmbeddingProviderConfig(
        provider_name="AWS Bedrock",
        adapter_id="bedrock|88199741-8d7e-4e8c-9d92-d76b0dc20c91",
        required_env_vars=[
            "AWS_EMBEDDING_ACCESS_KEY_ID",
            "AWS_EMBEDDING_SECRET_ACCESS_KEY",
            "AWS_EMBEDDING_REGION_NAME",
            "BEDROCK_EMBEDDING_MODEL",
        ],
        metadata_builder=build_bedrock_embedding_metadata,
    ),
    "vertexai": EmbeddingProviderConfig(
        provider_name="Vertex AI",
        adapter_id="vertexai|457a256b-e74f-4251-98a0-8864aafb42a5",
        required_env_vars=[
            "VERTEXAI_EMBEDDING_PROJECT",
            "VERTEXAI_EMBEDDING_JSON_CREDENTIALS",
            "VERTEXAI_EMBEDDING_MODEL",
        ],
        metadata_builder=build_vertexai_embedding_metadata,
    ),
    "ollama": EmbeddingProviderConfig(
        provider_name="Ollama",
        adapter_id="ollama|d58d7080-55a9-4542-becd-8433528e127b",
        required_env_vars=["OLLAMA_EMBEDDING_BASE_URL", "OLLAMA_EMBEDDING_MODEL"],
        metadata_builder=build_ollama_embedding_metadata,
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


def get_provider_config(provider_key: str) -> EmbeddingProviderConfig:
    """Get provider configuration by key.

    Args:
        provider_key: Provider key (e.g., 'openai', 'azure_openai')

    Returns:
        Provider configuration

    Raises:
        KeyError: If provider key is not found
    """
    return PROVIDER_CONFIGS[provider_key]
