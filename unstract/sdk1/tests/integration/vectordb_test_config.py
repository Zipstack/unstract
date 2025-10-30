"""Configuration for VectorDB adapter integration tests.

This module provides configuration for testing VectorDB adapters across
different providers. Each provider configuration includes:
- Adapter ID from source code
- Required environment variables
- Metadata builder function
- Skip conditions based on environment

VectorDB adapters use LlamaIndex (not LiteLLM like LLM/Embedding).
"""

import os
from typing import Any


class VectorDBProviderConfig:
    """Configuration for a VectorDB provider."""

    def __init__(
        self,
        provider_name: str,
        adapter_id: str,
        required_env_vars: list[str],
        metadata_builder: callable,
        skip_reason: str | None = None,
    ):
        """Initialize VectorDB provider configuration.

        Args:
            provider_name: Human-readable provider name
            adapter_id: Exact adapter ID from source code (format: "provider|uuid")
            required_env_vars: List of environment variables required for this provider
            metadata_builder: Function that builds adapter metadata from env vars
            skip_reason: Optional reason to skip this provider (e.g., "Requires local setup")
        """
        self.provider_name = provider_name
        self.adapter_id = adapter_id
        self.required_env_vars = required_env_vars
        self.metadata_builder = metadata_builder
        self.skip_reason = skip_reason

    def build_metadata(self) -> dict[str, Any]:
        """Build adapter metadata dictionary from environment variables.

        Returns:
            Dictionary containing adapter configuration

        Raises:
            ValueError: If required environment variables are not set
        """
        return self.metadata_builder()

    def is_available(self) -> bool:
        """Check if this provider is available for testing.

        Returns:
            True if all required environment variables are set, False otherwise
        """
        if self.skip_reason:
            return False
        return all(os.getenv(var) for var in self.required_env_vars)


# Metadata builder functions for each provider


def build_milvus_metadata() -> dict[str, Any]:
    """Build Milvus adapter metadata from environment variables."""
    return {
        "uri": os.getenv("MILVUS_URI"),
        "token": os.getenv("MILVUS_TOKEN", ""),
        "embedding_dimension": int(
            os.getenv("MILVUS_EMBEDDING_DIMENSION", "1536")
        ),
        "vector_db_name": os.getenv("MILVUS_COLLECTION_NAME", "test_collection"),
    }


def build_pinecone_metadata() -> dict[str, Any]:
    """Build Pinecone adapter metadata from environment variables."""
    spec = os.getenv("PINECONE_SPEC", "serverless")
    metadata = {
        "api_key": os.getenv("PINECONE_API_KEY"),
        "environment": os.getenv("PINECONE_ENVIRONMENT"),
        "spec": spec,
        "embedding_dimension": int(
            os.getenv("PINECONE_EMBEDDING_DIMENSION", "1536")
        ),
        "vector_db_name": os.getenv("PINECONE_INDEX_NAME", "test-index"),
    }

    # Add spec-specific fields
    if spec == "serverless":
        metadata["cloud"] = os.getenv("PINECONE_CLOUD", "aws")
        metadata["region"] = os.getenv("PINECONE_REGION", "us-east-1")

    return metadata


def build_qdrant_metadata() -> dict[str, Any]:
    """Build Qdrant adapter metadata from environment variables."""
    return {
        "url": os.getenv("QDRANT_URL"),
        "api_key": os.getenv("QDRANT_API_KEY", ""),
        "embedding_dimension": int(
            os.getenv("QDRANT_EMBEDDING_DIMENSION", "1536")
        ),
        "vector_db_name": os.getenv("QDRANT_COLLECTION_NAME", "test_collection"),
    }


def build_weaviate_metadata() -> dict[str, Any]:
    """Build Weaviate adapter metadata from environment variables."""
    return {
        "url": os.getenv("WEAVIATE_URL"),
        "api_key": os.getenv("WEAVIATE_API_KEY"),
        "embedding_dimension": int(
            os.getenv("WEAVIATE_EMBEDDING_DIMENSION", "1536")
        ),
        "vector_db_name": os.getenv("WEAVIATE_COLLECTION_NAME", "test_collection"),
    }


def build_postgres_metadata() -> dict[str, Any]:
    """Build Postgres adapter metadata from environment variables."""
    return {
        "host": os.getenv("POSTGRES_HOST"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "database": os.getenv("POSTGRES_DATABASE"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "schema": os.getenv("POSTGRES_SCHEMA", "public"),
        "enable_ssl": os.getenv("POSTGRES_ENABLE_SSL", "true").lower() == "true",
        "embedding_dimension": int(
            os.getenv("POSTGRES_EMBEDDING_DIMENSION", "1536")
        ),
        "vector_db_name": os.getenv("POSTGRES_TABLE_NAME", "test_table"),
    }


def build_supabase_metadata() -> dict[str, Any]:
    """Build Supabase adapter metadata from environment variables."""
    return {
        "host": os.getenv("SUPABASE_HOST"),
        "port": int(os.getenv("SUPABASE_PORT", "5432")),
        "database": os.getenv("SUPABASE_DATABASE"),
        "user": os.getenv("SUPABASE_USER"),
        "password": os.getenv("SUPABASE_PASSWORD"),
        "embedding_dimension": int(
            os.getenv("SUPABASE_EMBEDDING_DIMENSION", "1536")
        ),
        "vector_db_name": os.getenv("SUPABASE_COLLECTION_NAME", "test_collection"),
    }


# Provider configurations
# Adapter IDs verified from source code in unstract/sdk1/src/unstract/sdk1/adapters/vectordb/

PROVIDER_CONFIGS = {
    "milvus": VectorDBProviderConfig(
        provider_name="Milvus",
        adapter_id="milvus|3f42f6f9-4b8e-4546-95f3-22ecc9aca442",
        required_env_vars=["MILVUS_URI"],
        metadata_builder=build_milvus_metadata,
    ),
    "pinecone": VectorDBProviderConfig(
        provider_name="Pinecone",
        adapter_id="pinecone|83881133-485d-4ecc-b1f7-0009f96dc74a",
        required_env_vars=["PINECONE_API_KEY", "PINECONE_ENVIRONMENT"],
        metadata_builder=build_pinecone_metadata,
    ),
    "qdrant": VectorDBProviderConfig(
        provider_name="Qdrant",
        adapter_id="qdrant|41f64fda-2e4c-4365-89fd-9ce91bee74d0",
        required_env_vars=["QDRANT_URL"],
        metadata_builder=build_qdrant_metadata,
    ),
    "weaviate": VectorDBProviderConfig(
        provider_name="Weaviate",
        adapter_id="weaviate|294e08df-4e4a-40f2-8f0d-9e4940180ccc",
        required_env_vars=["WEAVIATE_URL", "WEAVIATE_API_KEY"],
        metadata_builder=build_weaviate_metadata,
    ),
    "postgres": VectorDBProviderConfig(
        provider_name="Postgres",
        adapter_id="postgres|70ab6cc2-e86a-4e5a-896f-498a95022d34",
        required_env_vars=[
            "POSTGRES_HOST",
            "POSTGRES_DATABASE",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
        ],
        metadata_builder=build_postgres_metadata,
    ),
    "supabase": VectorDBProviderConfig(
        provider_name="Supabase",
        adapter_id="supabase|e6998e3c-3595-48c0-a190-188dbd803858",
        required_env_vars=[
            "SUPABASE_HOST",
            "SUPABASE_DATABASE",
            "SUPABASE_USER",
            "SUPABASE_PASSWORD",
        ],
        metadata_builder=build_supabase_metadata,
    ),
}


def get_available_providers() -> list[str]:
    """Get list of provider keys that are available for testing.

    Returns:
        List of provider keys with all required environment variables set
    """
    return [key for key, config in PROVIDER_CONFIGS.items() if config.is_available()]


# Get list of available providers for pytest parametrization
AVAILABLE_PROVIDERS = get_available_providers()

# Add dummy provider if no providers are configured to prevent pytest from failing
if not AVAILABLE_PROVIDERS:
    AVAILABLE_PROVIDERS = ["dummy"]
    PROVIDER_CONFIGS["dummy"] = VectorDBProviderConfig(
        provider_name="Dummy",
        adapter_id="dummy|00000000-0000-0000-0000-000000000000",
        required_env_vars=[],
        metadata_builder=lambda: {},
        skip_reason="No VectorDB providers configured",
    )
